from typing import List, Optional
import uuid
import math

from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import settings
from app.database import get_db
from app.deps_supabase import SupabasePrincipal, require_supabase_roles
from app.models.school import School
from app.models.student import Student
from app.models.payment import Invoice, Payment, PaymentAllocation, Receipt
from app.models.paynow import PaynowAttempt
from app.services.crypto import encrypt, decrypt
from app.services.paynow import initiate_transaction, poll_transaction, verify_hash, _validate_poll_url, _validate_browser_url
from app.services.money import invoice_balance, is_valid_payment_amount, next_receipt_number, to_decimal
from app.services.audit import write_audit

router = APIRouter(prefix="/paynow", tags=["paynow"])


class PaynowSettingsUpdate(BaseModel):
    integration_id: str
    integration_key: str
    test_mode: bool = True
    school_id: Optional[int] = None


class PaynowInitiateRequest(BaseModel):
    student_id: Optional[int] = None
    invoice_ids: Optional[List[int]] = None
    amount: Optional[float] = None
    school_id: Optional[int] = None
    return_url: Optional[str] = None
    result_url: Optional[str] = None



def _verified_paid_confirmation(polled: dict, attempt: PaynowAttempt) -> bool:
    """Bind a signed Paynow Paid response to the exact local checkout."""
    if not polled.get("hash_verified"):
        return False
    provider_reference = polled.get("reference") or polled.get("Reference")
    provider_amount = polled.get("amount") or polled.get("Amount")
    if provider_reference != attempt.reference or provider_amount is None:
        return False
    try:
        from decimal import Decimal, InvalidOperation
        received = Decimal(str(provider_amount))
        expected = Decimal(str(attempt.amount))
        if not received.is_finite() or not expected.is_finite():
            return False
    except (InvalidOperation, ValueError, TypeError):
        return False
    return received == expected


def _record_verified_payment(db: Session, attempt: PaynowAttempt) -> bool:
    """Create one payment/allocation/receipt atomically for a verified attempt.

    The attempt row is locked by the caller. Locking the school serializes
    receipt-number allocation across different checkouts in the same tenant.
    """
    ref_key = f"paynow:{attempt.id}"
    existing = db.query(Payment).filter(Payment.reference == ref_key).first()
    if existing is not None:
        return True

    school = db.query(School).filter(
        School.id == attempt.school_id
    ).with_for_update().first()
    if school is None:
        return False

    invoice = None
    from decimal import Decimal
    if attempt.invoice_id is not None:
        invoice = db.query(Invoice).filter(
            Invoice.id == attempt.invoice_id
        ).with_for_update().first()
        if (
            invoice is None
            or invoice.school_id != attempt.school_id
            or invoice.student_id != attempt.student_id
            or invoice.currency != attempt.currency
            or invoice.status == "void"
        ):
            return False
        # Multiple checkout attempts can be created against the same balance.
        # Recheck under the invoice lock before accepting the provider payment.
        if Decimal(str(attempt.amount)) > invoice_balance(db, invoice):
            return False
    else:
        student_invoices = db.query(Invoice).filter(
            Invoice.school_id == attempt.school_id,
            Invoice.student_id == attempt.student_id,
            Invoice.currency == attempt.currency,
            Invoice.status != "void",
        ).order_by(Invoice.id).with_for_update().all()
        outstanding = sum(
            (invoice_balance(db, item) for item in student_invoices),
            Decimal("0"),
        )
        if Decimal(str(attempt.amount)) > outstanding:
            return False

    payment = Payment(
        school_id=attempt.school_id,
        student_id=attempt.student_id,
        amount=attempt.amount,
        currency=attempt.currency,
        method="paynow",
        reference=ref_key,
    )
    db.add(payment)
    db.flush()

    if invoice is not None:
        balance = invoice_balance(db, invoice)
        allocation = min(balance, __import__("decimal").Decimal(str(payment.amount)))
        if allocation > 0:
            db.add(PaymentAllocation(
                school_id=payment.school_id,
                payment_id=payment.id,
                invoice_id=invoice.id,
                amount=allocation,
            ))
    else:
        from app.services.money import allocate_payment
        allocate_payment(db, payment, None)

    db.add(Receipt(
        school_id=attempt.school_id,
        payment_id=payment.id,
        receipt_number=next_receipt_number(db, attempt.school_id),
    ))
    return True


def _student_usd_balance(db: Session, school_id: int, student_id: int):
    from decimal import Decimal

    invoices = db.query(Invoice).filter(
        Invoice.school_id == school_id,
        Invoice.student_id == student_id,
        Invoice.currency == "USD",
        Invoice.status != "void",
    ).all()
    return sum(
        (invoice_balance(db, invoice) for invoice in invoices),
        Decimal("0"),
    )


def _sid(principal: SupabasePrincipal, requested: Optional[int]) -> int:
    if principal.is_admin:
        if requested is None:
            raise HTTPException(status_code=400, detail="school_id required")
        return requested
    if principal.school_id is None:
        raise HTTPException(status_code=403, detail="School context required")
    return principal.school_id


@router.post("/settings")
def update_settings(payload: PaynowSettingsUpdate, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar')), db: Session = Depends(get_db)):
    sid = _sid(principal, payload.school_id)
    if not principal.is_admin and principal.role not in ("owner", "headmaster"):
        raise HTTPException(status_code=403, detail="Not allowed")
    school = db.get(School, sid)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    school.paynow_integration_id = payload.integration_id
    school.paynow_integration_key = encrypt(payload.integration_key)
    school.paynow_test_mode = payload.test_mode
    db.commit()
    write_audit(db, principal, "paynow.settings.update", "school", school.id, {}, school_id=sid)
    return {"status": "updated"}


@router.get("/settings")
def get_settings(school_id: Optional[int] = None, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar')), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id)
    school = db.get(School, sid)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    return {
        "integration_id": school.paynow_integration_id,
        "test_mode": school.paynow_test_mode,
        "has_key": bool(school.paynow_integration_key),
    }


@router.post("/initiate")
def initiate_payment(payload: PaynowInitiateRequest, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar', 'student', 'parent')), db: Session = Depends(get_db)):
    # determine school
    if principal.role == 'student':
        linked = db.query(Student).filter(
            Student.portal_user_id == principal.user_id,
            Student.school_id == principal.school_id,
        ).all()
        if len(linked) != 1:
            raise HTTPException(status_code=403, detail='Student account is not uniquely linked')
        if linked[0].status != 'active':
            raise HTTPException(status_code=403, detail='Student account is inactive')
        if payload.student_id is not None and payload.student_id != linked[0].id:
            raise HTTPException(status_code=403, detail='Access denied')
        payload.student_id = linked[0].id
        sid = linked[0].school_id
    elif principal.role == 'parent':
        if payload.student_id is None or principal.school_id is None:
            raise HTTPException(status_code=422, detail='Select a linked learner for payment')
        link = db.execute(text("SELECT 1 FROM public.guardian_links gl JOIN public.contacts c ON c.id=gl.contact_id AND c.school_id=gl.school_id JOIN public.students s ON s.id=c.student_id AND s.school_id=c.school_id WHERE gl.profile_id=:profile_id AND gl.school_id=:school_id AND c.student_id=:student_id AND gl.is_active=true AND gl.verified_at IS NOT NULL AND s.status='active' LIMIT 1"), {'profile_id': str(principal.auth_user_id), 'school_id': principal.school_id, 'student_id': payload.student_id}).first()
        if link is None:
            raise HTTPException(status_code=404, detail='Linked student not found')
        sid = principal.school_id
    elif payload.student_id:
        student = db.get(Student, payload.student_id)
        if student is None or student.status != "active":
            raise HTTPException(status_code=404, detail="Active student not found")
        sid = student.school_id
        if not principal.is_admin and principal.school_id != sid and principal.role not in ("student", "parent"):
            raise HTTPException(status_code=403, detail="Access denied")
    elif principal.role in ("student", "parent"):
        student = db.query(Student).filter(Student.portal_user_id == principal.user_id).first()
        if student is None:
            raise HTTPException(status_code=404, detail="No student linked")
        payload.student_id = student.id
        sid = student.school_id
    else:
        sid = _sid(principal, payload.school_id)

    school = db.get(School, sid)
    if school is None or not school.paynow_integration_id or not school.paynow_integration_key:
        raise HTTPException(status_code=400, detail="Paynow not configured for school")

    # Until the attempt schema supports multiple allocations, accept one invoice per checkout.
    if payload.invoice_ids and len(set(payload.invoice_ids)) != 1:
        raise HTTPException(status_code=422, detail="Paynow checkout currently supports one invoice at a time")
    if payload.invoice_ids:
        selected_invoice = db.query(Invoice).filter(Invoice.id == payload.invoice_ids[0], Invoice.school_id == sid, Invoice.status != 'void').first()
        if selected_invoice is None:
            raise HTTPException(status_code=404, detail="Invoice not found in this school")
        if selected_invoice.currency != "USD":
            raise HTTPException(status_code=422, detail="Paynow checkout currently supports USD invoices only")
        if payload.student_id is not None and payload.student_id != selected_invoice.student_id:
            raise HTTPException(status_code=422, detail="Invoice does not belong to the selected student")
        payload.student_id = selected_invoice.student_id

    if payload.student_id is None:
        raise HTTPException(status_code=422, detail="A student or invoice must be selected for checkout")

    # determine amount
    if payload.amount is not None:
        amount = payload.amount
        if not math.isfinite(amount) or amount <= 0:
            raise HTTPException(status_code=422, detail="Payment amount must be a finite positive value")
        if payload.invoice_ids and to_decimal(amount) > invoice_balance(db, selected_invoice):
            raise HTTPException(status_code=422, detail="Payment amount exceeds invoice balance")
        if not payload.invoice_ids and payload.student_id and to_decimal(amount) > _student_usd_balance(db, sid, payload.student_id):
            raise HTTPException(status_code=422, detail="Payment amount exceeds the student balance")
    elif payload.invoice_ids:
        invoices = db.query(Invoice).filter(
            Invoice.id.in_(payload.invoice_ids),
            Invoice.school_id == sid,
        ).all()
        amount = sum(
            (invoice_balance(db, inv) for inv in invoices),
            to_decimal(0),
        )
    elif payload.student_id:
        amount = _student_usd_balance(db, sid, payload.student_id)
    else:
        raise HTTPException(status_code=400, detail="amount or student_id or invoice_ids required")

    if not is_valid_payment_amount(amount):
        raise HTTPException(
            status_code=422,
            detail="Payment amount must be positive and have no more than two decimal places",
        )
    amount = to_decimal(amount)

    integration_key = decrypt(school.paynow_integration_key)
    reference = f"PN-{uuid.uuid4().hex[:12].upper()}"

    attempt = PaynowAttempt(
        school_id=sid,
        student_id=payload.student_id,
        invoice_id=(payload.invoice_ids[0] if payload.invoice_ids else None),
        reference=reference,
        amount=amount,
        currency="USD",
        status="created",
    )
    db.add(attempt)
    db.flush()

    return_url = settings.paynow_return_url
    result_url = settings.paynow_result_url

    resp = initiate_transaction(
        integration_id=school.paynow_integration_id,
        integration_key=integration_key,
        reference=reference,
        amount=amount,
        return_url=return_url,
        result_url=result_url,
        additional_info=f"School {school.code}",
    )

    if resp.get("status", "").lower() != "ok":
        attempt.status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail=resp.get("error") or "Paynow initiation failed")

    browser_url = resp.get("BrowserUrl") or resp.get("browserurl")
    poll_url = resp.get("PollUrl") or resp.get("pollurl")
    try:
        if not browser_url or not poll_url:
            raise ValueError("Paynow did not return both checkout and polling URLs")
        attempt.browser_url = _validate_browser_url(browser_url)
        attempt.poll_url = _validate_poll_url(poll_url)
    except ValueError:
        attempt.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=502,
            detail="Paynow returned an invalid checkout response. Please contact your school before retrying.",
        )

    attempt.status = "sent"
    attempt.hash_verified = bool(resp.get("hash_verified"))
    db.commit()

    return {
        "attempt_id": attempt.id,
        "browser_url": attempt.browser_url,
        "poll_url": attempt.poll_url,
        "amount": amount,
    }
@router.post("/webhook")
async def paynow_webhook(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    data = {}
    for key in form.keys():
        data[key] = form.get(key)

    reference = data.get("reference") or data.get("Reference")
    attempt = None
    if reference:
        attempt = db.query(PaynowAttempt).filter(PaynowAttempt.reference == reference).with_for_update().first()
    if attempt is None:
        poll_url = data.get("pollurl") or data.get("PollUrl")
        if poll_url:
            attempt = db.query(PaynowAttempt).filter(PaynowAttempt.poll_url == poll_url).with_for_update().first()
    if attempt is None:
        return {"status": "ignored"}
    # A late cancellation/failure notification must never downgrade a
    # successfully settled checkout.
    if attempt.status == "paid":
        return {"status": "already paid"}

    school = db.get(School, attempt.school_id)
    if school is None or not school.paynow_integration_key:
        return {"status": "school not configured"}
    integration_key = decrypt(school.paynow_integration_key)

    polled = {}
    if attempt.poll_url:
        polled = poll_transaction(attempt.poll_url, integration_key)
    attempt.hash_verified = bool(polled.get("hash_verified"))

    status_val = (polled.get("Status") or polled.get("status") or data.get("status") or data.get("Status") or "").lower()

    if status_val == "paid" and not _verified_paid_confirmation(polled, attempt):
        attempt.status = "unverified"
        db.commit()
        return {"status": "payment confirmation hash could not be verified"}
    if status_val == "paid":
        if _record_verified_payment(db, attempt):
            attempt.status = "paid"
        else:
            attempt.status = "unverified"
            db.commit()
            return {"status": "verified payment could not be matched to its invoice"}
    elif status_val in ("cancelled", "failed", "disputed"):
        attempt.status = status_val
    else:
        attempt.status = "sent"

    attempt.paynow_reference = data.get("paynowreference") or data.get("PaynowReference") or attempt.paynow_reference
    db.commit()
    return {"status": "ok"}

@router.get("/attempts")
def list_attempts(school_id: Optional[int] = None, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar')), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id) if (principal.is_admin or school_id is not None) else principal.school_id
    if sid is None:
        raise HTTPException(status_code=403, detail="School context required")
    attempts = db.query(PaynowAttempt).filter(PaynowAttempt.school_id == sid).order_by(PaynowAttempt.id.desc()).all()
    return [
        {
            "id": a.id,
            "reference": a.reference,
            "student_id": a.student_id,
            "amount": float(a.amount),
            "currency": a.currency,
            "status": a.status,
            "hash_verified": a.hash_verified,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in attempts
    ]


@router.post("/reconcile")
def reconcile(principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar')), db: Session = Depends(get_db)):
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    pending = db.query(PaynowAttempt).filter(PaynowAttempt.status.in_(("sent", "unverified"))).with_for_update(skip_locked=True).all()
    updated = 0
    for att in pending:
        school = db.get(School, att.school_id)
        if not school or not school.paynow_integration_key:
            continue
        key = decrypt(school.paynow_integration_key)
        if not att.poll_url:
            continue
        from app.services.paynow import poll_transaction
        polled = poll_transaction(att.poll_url, key)
        st = (polled.get("Status") or polled.get("status") or "").lower()
        if st == "paid" and not _verified_paid_confirmation(polled, att):
            att.status = "unverified"
            updated += 1
            continue
        if st == "paid" and att.status != "paid":
            if _record_verified_payment(db, att):
                att.status = "paid"
            else:
                att.status = "unverified"
            updated += 1
        elif st in ("cancelled", "failed"):
            att.status = st
            updated += 1
    db.commit()
    return {"updated": updated}

