from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_principal, get_supabase_auth_identity, Principal
from app.models.school import School
from app.models.student import Student, Contact
from app.models.payment import Invoice
from app.models.profile import Profile
from app.models.user import User
from app.services.auth import hash_password
from app.services.ids import verify_pin
from app.services.money import invoice_balance, student_balance
from app.services.audit import write_audit

router = APIRouter(prefix="/portal", tags=["portal"])


class PortalRegisterRequest(BaseModel):
    school_code: str
    student_number: str
    pin: str
    phone: Optional[str] = None


class PortalFeeItem(BaseModel):
    invoice_number: str
    total: float
    balance: float
    currency: str
    issued_at: Optional[str] = None


@router.post("/register", status_code=status.HTTP_201_CREATED)
def portal_register(
    payload: PortalRegisterRequest,
    identity: dict = Depends(get_supabase_auth_identity),
    db: Session = Depends(get_db),
):
    """Link a verified Supabase identity to a learner using the school's one-time PIN."""
    if not identity.get("email") or not identity.get("email_confirmed_at"):
        raise HTTPException(status_code=403, detail="Verify your email address before activating your portal account.")

    school = db.query(School).filter(School.code == payload.school_code.strip()).first()
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    # Lock the learner row so concurrent activation attempts cannot both
    # consume the same one-time PIN and create separate local accounts.
    student = db.query(Student).filter(
        Student.school_id == school.id,
        Student.student_number == payload.student_number.strip(),
    ).with_for_update().first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student record not found")
    if student.status != "active":
        raise HTTPException(status_code=403, detail="Only active learners can activate a portal account.")
    if student.activated_at is not None or student.portal_user_id is not None:
        raise HTTPException(status_code=409, detail="This learner account has already been activated. Contact your school administrator.")
    if student.activation_pin_hash is None:
        raise HTTPException(status_code=400, detail="No active activation PIN exists for this learner.")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if student.activation_expires_at is not None and student.activation_expires_at < now:
        raise HTTPException(status_code=400, detail="Activation PIN has expired. Request a new slip from your school.")
    if not verify_pin(payload.pin, student.activation_pin_hash):
        raise HTTPException(status_code=400, detail="Invalid activation PIN")

    email = identity["email"].strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="This email is already linked to a Chikoro account. Use account recovery or contact your school.")

    profile = db.get(Profile, identity["id"])
    if profile is None:
        profile = Profile(id=identity["id"], role="pending", is_active=False)
        db.add(profile)
        db.flush()
    if profile.local_user_id is not None or profile.is_active:
        raise HTTPException(status_code=409, detail="This Supabase account is already linked to a Chikoro profile.")

    user = User(
        email=email,
        full_name=f"{student.first_name} {student.last_name}",
        password_hash=hash_password("supabase-managed-" + identity["id"]),
        role="student",
        school_id=school.id,
        is_active=True,
    )
    db.add(user)
    db.flush()

    profile.local_user_id = user.id
    profile.role = "student"
    profile.school_id = school.id
    profile.is_active = True
    profile.updated_at = now
    student.portal_user_id = user.id
    student.activated_at = now
    student.activation_pin_hash = None
    if payload.phone:
        db.add(Contact(school_id=school.id, student_id=student.id, name="Self", phone=payload.phone, is_primary=True))

    db.commit()
    write_audit(db, user.id, "portal.register", "student", student.id, {"email": email}, school_id=school.id)
    return {"status": "activated", "email": email, "student_number": student.student_number}


@router.get("/fee-status")
def portal_fee_status(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    if principal.role not in ("student", "parent", "admin"):
        raise HTTPException(status_code=403, detail="Portal users only")
    student = db.query(Student).filter(Student.portal_user_id == principal.user_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail="No learner record is linked to this account")
    invoices = db.query(Invoice).filter(
        Invoice.school_id == student.school_id,
        Invoice.student_id == student.id,
    ).order_by(Invoice.id).all()
    items = []
    for inv in invoices:
        bal = invoice_balance(db, inv)
        items.append({
            "invoice_number": inv.invoice_number,
            "total": float(inv.total),
            "balance": float(bal),
            "currency": inv.currency,
            "issued_at": inv.issued_at.isoformat() if inv.issued_at else None,
        })
    total_balance = student_balance(db, student.school_id, student.id)
    return {
        "student_number": student.student_number,
        "name": f"{student.first_name} {student.last_name}",
        "invoices": items,
        "total_balance": float(total_balance),
    }


@router.get("/me")
def portal_me(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    user = db.get(User, principal.user_id)
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": principal.role, "school_id": principal.school_id}
