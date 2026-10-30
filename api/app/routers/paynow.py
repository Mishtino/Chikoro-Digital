from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_principal, Principal
from app.models.school import School
from app.models.student import Student
from app.models.payment import Invoice, Payment, PaymentAllocation, Receipt
from app.models.paynow import PaynowAttempt
from app.services.crypto import encrypt, decrypt
from app.services.paynow import initiate_transaction, poll_transaction, verify_hash
from app.services.money import invoice_balance, student_balance
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


def _sid(principal: Principal, requested: Optional[int]) -> int:
    if principal.is_admin:
        if requested is None:
            raise HTTPException(status_code=400, detail="school_id required")
        return requested
    if principal.school_id is None:
        raise HTTPException(status_code=403, detail="School context required")
    return principal.school_id


@router.post("/settings")
def update_settings(payload: PaynowSettingsUpdate, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
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
def get_settings(school_id: Optional[int] = None, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
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
def initiate_payment(payload: PaynowInitiateRequest, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    # determine school
    if payload.student_id:
        student = db.get(Student, payload.student_id)
        if student is None:
            raise HTTPException(status_code=404, detail="Student not found")
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

    # determine amount
    if payload.amount is not None:
        amount = payload.amount
    elif payload.invoice_ids:
        invoices = db.query(Invoice).filter(Invoice.id.in_(payload.invoice_ids), Invoice.school_id == sid).all()
        amount = sum(float(invoice_balance(db, inv)) for inv in invoices)
    elif payload.student_id:
        amount = float(student_balance(db, sid, payload.student_id))
    else:
        raise HTTPException(status_code=400, detail="amount or student_id or invoice_ids required")

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Nothing to pay")

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

    return_url = payload.return_url or settings.paynow_return_url
    result_url = payload.result_url or settings.paynow_result_url

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

    attempt.status = "sent"
    attempt.browser_url = resp.get("BrowserUrl") or resp.get("browserurl")
    attempt.poll_url = resp.get("PollUrl") or resp.get("pollurl")
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
        attempt = db.query(PaynowAttempt).filter(PaynowAttempt.reference == reference).first()
    if attempt is None:
        poll_url = data.get("pollurl") or data.get("PollUrl")
        if poll_url:
            attempt = db.query(PaynowAttempt).filter(PaynowAttempt.poll_url == poll_url).first()
    if attempt is None:
        return {"status": "ignored"}

    school = db.get(School, attempt.school_id)
    if school is None or not school.paynow_integration_key:
        return {"status": "school not configured"}
    integration_key = decrypt(school.paynow_integration_key)

    ping_verified = verify_hash(data, integration_key)

    polled = {}
    if attempt.poll_url:
        polled = poll_transaction(attempt.poll_url, integration_key)
    attempt.hash_verified = bool(ping_verified or polled.get("hash_verified"))

    status_val = (polled.get("Status") or polled.get("status") or data.get("status") or data.get("Status") or "").lower()

    if status_val == "paid":
        ref_key = f"paynow:{attempt.id}"
        existing = db.query(Payment).filter(Payment.reference == ref_key).first()
        if existing is None:
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
            if attempt.invoice_id:
                inv = db.get(Invoice, attempt.invoice_id)
                if inv is not None:
                    from app.services.money import invoice_balance
                    from app.models.payment import PaymentAllocation
                    bal = invoice_balance(db, inv)
                    alloc = min(bal, __import__("decimal").Decimal(str(payment.amount)))
                    if alloc > 0:
                        db.add(PaymentAllocation(school_id=payment.school_id, payment_id=payment.id, invoice_id=inv.id, amount=alloc))
            else:
                from app.services.money import allocate_payment as alloc
                alloc(db, payment, None)
            count = db.query(Receipt).filter(Receipt.school_id == attempt.school_id).count()
            db.add(Receipt(school_id=attempt.school_id, payment_id=payment.id, receipt_number=f"RCP-{count + 1:05d}"))
        attempt.status = "paid"
    elif status_val in ("cancelled", "failed", "disputed"):
        attempt.status = status_val
    else:
        attempt.status = "sent"

    attempt.paynow_reference = data.get("paynowreference") or data.get("PaynowReference") or attempt.paynow_reference
    db.commit()
    return {"status": "ok"}

@router.get("/attempts")
def list_attempts(school_id: Optional[int] = None, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
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
def reconcile(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    pending = db.query(PaynowAttempt).filter(PaynowAttempt.status == "sent").all()
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
        if st == "paid" and att.status != "paid":
            ref_key = f"paynow:{att.id}"
            existing = db.query(Payment).filter(Payment.reference == ref_key).first()
            if existing is None:
                payment = Payment(
                    school_id=att.school_id,
                    student_id=att.student_id,
                    amount=att.amount,
                    currency=att.currency,
                    method="paynow",
                    reference=ref_key,
                )
                db.add(payment)
                db.flush()
                if att.invoice_id:
                    inv = db.get(Invoice, att.invoice_id)
                    if inv is not None:
                        from app.services.money import invoice_balance
                        from app.models.payment import PaymentAllocation
                        bal = invoice_balance(db, inv)
                        alloc_amt = min(bal, __import__("decimal").Decimal(str(payment.amount)))
                        if alloc_amt > 0:
                            db.add(PaymentAllocation(school_id=payment.school_id, payment_id=payment.id, invoice_id=inv.id, amount=alloc_amt))
                else:
                    from app.services.money import allocate_payment as alloc
                    alloc(db, payment, None)
                count = db.query(Receipt).filter(Receipt.school_id == att.school_id).count()
                db.add(Receipt(school_id=att.school_id, payment_id=payment.id, receipt_number=f"RCP-{count + 1:05d}"))
            att.status = "paid"
            updated += 1
        elif st in ("cancelled", "failed"):
            att.status = st
            updated += 1
    db.commit()
    return {"updated": updated}

