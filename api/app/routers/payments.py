from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.deps_supabase import SupabasePrincipal, require_supabase_roles
from app.models.payment import Invoice, InvoiceLine, Payment, PaymentAllocation, Receipt
from app.models.student import Student
from app.models.school import School
from app.services.money import allocate_payment, invoice_balance, is_valid_payment_amount, next_receipt_number, to_decimal
from app.services.audit import write_audit

router = APIRouter(prefix="/payments", tags=["payments"])


class PaymentCreate(BaseModel):
    student_id: int
    amount: Decimal
    currency: str = "USD"
    method: str = "manual"
    reference: Optional[str] = None
    invoice_ids: Optional[List[int]] = None
    school_id: Optional[int] = None


class VoidRequest(BaseModel):
    reason: str


def _sid(principal: SupabasePrincipal, requested: Optional[int]) -> int:
    # Payment routes are school-scoped; platform identities must use the
    # separately permissioned platform APIs, never a legacy is_admin bypass.
    if principal.is_admin or principal.school_id is None:
        raise HTTPException(status_code=403, detail="School-scoped access required")
    if requested is not None and requested != principal.school_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return principal.school_id


@router.post("", status_code=status.HTTP_201_CREATED)
def record_payment(payload: PaymentCreate, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar')), db: Session = Depends(get_db)):
    sid = _sid(principal, payload.school_id)
    student = db.get(Student, payload.student_id)
    if student is None or student.school_id != sid:
        raise HTTPException(status_code=404, detail="Student not found")
    # Consistent lock order with Paynow settlement: school first, then invoices.
    school = db.query(School).filter(School.id == sid).with_for_update().first()
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    if not is_valid_payment_amount(payload.amount):
        raise HTTPException(
            status_code=422,
            detail="Payment amount must be positive and have no more than two decimal places",
        )
    amount = to_decimal(payload.amount)
    currency = payload.currency.upper()
    if len(currency) != 3 or not currency.isalpha():
        raise HTTPException(status_code=422, detail="Currency must be a three-letter code")
    if payload.invoice_ids:
        requested_ids = set(payload.invoice_ids)
        if len(requested_ids) != len(payload.invoice_ids):
            raise HTTPException(status_code=422, detail="Duplicate invoice IDs are not allowed")
        selected_invoices = db.query(Invoice).filter(
            Invoice.id.in_(requested_ids),
            Invoice.school_id == sid,
            Invoice.student_id == payload.student_id,
            Invoice.currency == currency,
            Invoice.status != "void",
        ).order_by(Invoice.id).with_for_update().all()
        if len(selected_invoices) != len(requested_ids):
            raise HTTPException(status_code=404, detail="One or more invoices do not belong to this student and school")
        outstanding = sum(
            (invoice_balance(db, inv) for inv in selected_invoices),
            to_decimal(0),
        )
        if amount > outstanding:
            raise HTTPException(status_code=422, detail="Payment amount exceeds the selected invoices' outstanding balance")
    else:
        student_invoices = db.query(Invoice).filter(
            Invoice.school_id == sid,
            Invoice.student_id == payload.student_id,
            Invoice.currency == currency,
            Invoice.status != "void",
        ).order_by(Invoice.id).with_for_update().all()
        outstanding = sum(
            (invoice_balance(db, inv) for inv in student_invoices),
            to_decimal(0),
        )
        if to_decimal(payload.amount) > outstanding:
            raise HTTPException(status_code=422, detail="Payment amount exceeds the student's outstanding balance")
    reference = payload.reference.strip() if payload.reference else None
    if reference and db.query(Payment.id).filter(
        Payment.school_id == sid, Payment.reference == reference
    ).first():
        raise HTTPException(status_code=409, detail="Payment reference already exists for this school")
    payment = Payment(
        school_id=sid,
        student_id=payload.student_id,
        amount=amount,
        currency=payload.currency.upper(),
        method=payload.method,
        reference=reference,
        received_by_user_id=principal.user_id,
    )
    db.add(payment)
    db.flush()
    allocate_payment(db, payment, payload.invoice_ids)
    receipt = Receipt(
        school_id=sid,
        payment_id=payment.id,
        receipt_number=next_receipt_number(db, sid),
    )
    db.add(receipt)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        error_text = str(getattr(exc, "orig", exc))
        if (
            "uq_payment_reference_per_school" in error_text
            or "payments.school_id, payments.reference" in error_text
        ):
            raise HTTPException(
                status_code=409,
                detail="Payment reference already exists for this school",
            ) from exc
        raise
    db.refresh(payment)
    db.refresh(receipt)
    write_audit(db, principal, "payment.record", "payment", payment.id, {"amount": float(payload.amount), "method": payload.method}, school_id=sid)
    return {
        "payment_id": payment.id,
        "receipt_number": receipt.receipt_number,
        "allocated": True,
    }
@router.get("")
def list_payments(student_id: Optional[int] = Query(None), school_id: Optional[int] = Query(None), principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar')), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id)
    if sid is None:
        raise HTTPException(status_code=403, detail="School context required")
    q = db.query(Payment).filter(Payment.school_id == sid)
    if student_id is not None:
        q = q.filter(Payment.student_id == student_id)
    payments = q.order_by(Payment.id.desc()).all()
    return [
        {
            "id": p.id,
            "student_id": p.student_id,
            "amount": float(p.amount),
            "currency": p.currency,
            "method": p.method,
            "reference": p.reference,
            "received_at": p.received_at.isoformat() if p.received_at else None,
            "voided": p.voided,
        }
        for p in payments
    ]


@router.post("/{payment_id}/void")
def void_payment(payment_id: int, payload: VoidRequest, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster')), db: Session = Depends(get_db)):
    if principal.school_id is None or principal.is_admin:
        raise HTTPException(status_code=403, detail="School-scoped access required")
    # Use the same school -> payment lock order as payment recording and
    # Paynow settlement so a void cannot race with a new allocation.
    school = db.query(School).filter(
        School.id == principal.school_id
    ).with_for_update().first()
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    payment = db.query(Payment).filter(
        Payment.id == payment_id,
        Payment.school_id == principal.school_id,
    ).with_for_update().first()
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.voided:
        raise HTTPException(status_code=400, detail="Already voided")
    payment.voided = True
    payment.voided_at = datetime.now(timezone.utc).replace(tzinfo=None)
    payment.void_reason = payload.reason
    db.flush()
    write_audit(db, principal, "payment.void", "payment", payment.id, {"reason": payload.reason}, school_id=payment.school_id)
    return {"status": "voided"}


invoices_router = APIRouter(prefix="/invoices", tags=["invoices"])


@invoices_router.get("")
def list_invoices(student_id: Optional[int] = Query(None), school_id: Optional[int] = Query(None), principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar')), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id) if (principal.is_admin or school_id is not None) else principal.school_id
    if sid is None:
        raise HTTPException(status_code=403, detail="School context required")
    q = db.query(Invoice).filter(Invoice.school_id == sid)
    if student_id is not None:
        q = q.filter(Invoice.student_id == student_id)
    invoices = q.order_by(Invoice.id.desc()).all()
    result = []
    for inv in invoices:
        bal = invoice_balance(db, inv)
        paid_amt = float(inv.total) - float(bal)
        result.append({
            "id": inv.id,
            "student_id": inv.student_id,
            "invoice_number": inv.invoice_number,
            "term_id": inv.term_id,
            "total": float(inv.total),
            "currency": inv.currency,
            "status": inv.status,
            "issued_at": inv.issued_at.isoformat() if inv.issued_at else None,
            "balance": float(bal),
            "paid": paid_amt,
        })
    return result


@invoices_router.get("/{invoice_id}")
def get_invoice(invoice_id: int, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar')), db: Session = Depends(get_db)):
    if principal.school_id is None or principal.is_admin:
        raise HTTPException(status_code=403, detail="School-scoped access required")
    inv = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.school_id == principal.school_id,
    ).first()
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    lines = db.query(InvoiceLine).filter(
        InvoiceLine.invoice_id == inv.id,
        InvoiceLine.school_id == principal.school_id,
    ).all()
    bal = invoice_balance(db, inv)
    return {
        "id": inv.id,
        "student_id": inv.student_id,
        "invoice_number": inv.invoice_number,
        "total": float(inv.total),
        "currency": inv.currency,
        "status": inv.status,
        "balance": float(bal),
        "lines": [{"description": l.description, "amount": float(l.amount)} for l in lines],
    }

