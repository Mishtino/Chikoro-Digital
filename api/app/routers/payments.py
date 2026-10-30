from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_principal, Principal
from app.models.payment import Invoice, InvoiceLine, Payment, PaymentAllocation, Receipt
from app.models.student import Student
from app.services.money import allocate_payment, invoice_balance, student_balance, to_decimal
from app.services.audit import write_audit

router = APIRouter(prefix="/payments", tags=["payments"])


class PaymentCreate(BaseModel):
    student_id: int
    amount: float
    currency: str = "USD"
    method: str = "manual"
    reference: Optional[str] = None
    invoice_ids: Optional[List[int]] = None
    school_id: Optional[int] = None


class VoidRequest(BaseModel):
    reason: str


def _sid(principal: Principal, requested: Optional[int]) -> int:
    if principal.is_admin:
        if requested is None:
            raise HTTPException(status_code=400, detail="school_id required")
        return requested
    if principal.school_id is None:
        raise HTTPException(status_code=403, detail="School context required")
    return principal.school_id


@router.post("", status_code=status.HTTP_201_CREATED)
def record_payment(payload: PaymentCreate, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    sid = _sid(principal, payload.school_id)
    student = db.get(Student, payload.student_id)
    if student is None or student.school_id != sid:
        raise HTTPException(status_code=404, detail="Student not found")
    payment = Payment(
        school_id=sid,
        student_id=payload.student_id,
        amount=payload.amount,
        currency=payload.currency,
        method=payload.method,
        reference=payload.reference,
        received_by_user_id=principal.user_id,
    )
    db.add(payment)
    db.flush()
    allocate_payment(db, payment, payload.invoice_ids)
    count = db.query(Receipt).filter(Receipt.school_id == sid).count()
    receipt = Receipt(school_id=sid, payment_id=payment.id, receipt_number=f"RCP-{count + 1:05d}")
    db.add(receipt)
    db.commit()
    db.refresh(payment)
    db.refresh(receipt)
    write_audit(db, principal, "payment.record", "payment", payment.id, {"amount": float(payload.amount), "method": payload.method}, school_id=sid)
    return {
        "payment_id": payment.id,
        "receipt_number": receipt.receipt_number,
        "allocated": True,
    }
@router.get("")
def list_payments(student_id: Optional[int] = Query(None), school_id: Optional[int] = Query(None), principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id) if (principal.is_admin or school_id is not None) else principal.school_id
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
def void_payment(payment_id: int, payload: VoidRequest, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    if not principal.is_admin and principal.school_id != payment.school_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if payment.voided:
        raise HTTPException(status_code=400, detail="Already voided")
    payment.voided = True
    payment.voided_at = datetime.now(timezone.utc).replace(tzinfo=None)
    payment.void_reason = payload.reason
    db.commit()
    write_audit(db, principal, "payment.void", "payment", payment.id, {"reason": payload.reason}, school_id=payment.school_id)
    return {"status": "voided"}


invoices_router = APIRouter(prefix="/invoices", tags=["invoices"])


@invoices_router.get("")
def list_invoices(student_id: Optional[int] = Query(None), school_id: Optional[int] = Query(None), principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
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
def get_invoice(invoice_id: int, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if not principal.is_admin and principal.school_id != inv.school_id:
        raise HTTPException(status_code=403, detail="Access denied")
    lines = db.query(InvoiceLine).filter(InvoiceLine.invoice_id == inv.id).all()
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

