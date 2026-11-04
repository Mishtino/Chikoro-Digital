from datetime import datetime, timedelta, timezone
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
from app.models.guardian_link import GuardianLink
from app.models.user import User
from app.services.auth import hash_password
from app.services.ids import generate_pin, hash_pin, verify_pin
from app.services.money import invoice_balance, student_balance
from app.services.audit import write_audit

router = APIRouter(prefix="/portal", tags=["portal"])


class PortalRegisterRequest(BaseModel):
    school_code: str
    student_number: str
    pin: str
    phone: Optional[str] = None


class GuardianRegisterRequest(BaseModel):
    school_code: str
    contact_id: int
    pin: str


class PortalFeeItem(BaseModel):
    invoice_number: str
    total: float
    balance: float
    currency: str
    issued_at: Optional[str] = None


def _invoice_items(db: Session, student: Student):
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
            "id": inv.id,
        })
    return items


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


@router.post("/contacts/{contact_id}/guardian-pin")
def issue_guardian_activation_pin(
    contact_id: int,
    school_id: Optional[int] = None,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """Issue a short-lived PIN to school staff for a pre-verified guardian contact."""
    if principal.is_admin:
        if school_id is None:
            raise HTTPException(status_code=400, detail="school_id is required for a global administrator")
        sid = school_id
    else:
        if principal.role not in ("owner", "headmaster") or principal.school_id is None:
            raise HTTPException(status_code=403, detail="Only school owners or headmasters can issue guardian PINs")
        sid = principal.school_id

    contact = db.query(Contact).filter(
        Contact.id == contact_id,
        Contact.school_id == sid,
    ).with_for_update().first()
    if contact is None:
        raise HTTPException(status_code=404, detail="Guardian contact not found")
    if not contact.email:
        raise HTTPException(status_code=409, detail="A guardian email address must be recorded before issuing an activation PIN")
    if contact.guardian_activated_at is not None:
        raise HTTPException(status_code=409, detail="This contact has already activated a guardian account")

    pin = generate_pin()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    contact.guardian_activation_pin_hash = hash_pin(pin)
    contact.guardian_activation_expires_at = now + timedelta(hours=24)
    db.commit()
    write_audit(db, principal, "guardian.activation_pin.issue", "contact", contact.id, {"student_id": contact.student_id}, school_id=sid)
    return {
        "contact_id": contact.id,
        "guardian_email": contact.email,
        "activation_pin": pin,
        "expires_at": contact.guardian_activation_expires_at.isoformat(),
        "instruction": "Share this one-time PIN privately with the verified guardian. It will not be shown again.",
    }


@router.post("/guardian/register", status_code=status.HTTP_201_CREATED)
def guardian_register(
    payload: GuardianRegisterRequest,
    identity: dict = Depends(get_supabase_auth_identity),
    db: Session = Depends(get_db),
):
    """Activate a guardian only against a school-verified contact and one-time PIN."""
    if not identity.get("email") or not identity.get("email_confirmed_at"):
        raise HTTPException(status_code=403, detail="Verify your email address before activating your guardian account.")
    email = identity["email"].strip().lower()
    school = db.query(School).filter(School.code == payload.school_code.strip()).first()
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    contact = db.query(Contact).filter(
        Contact.id == payload.contact_id,
        Contact.school_id == school.id,
    ).with_for_update().first()
    if contact is None:
        raise HTTPException(status_code=404, detail="Guardian contact not found")
    if not contact.email or contact.email.strip().lower() != email:
        raise HTTPException(status_code=403, detail="Your confirmed email does not match the guardian contact held by the school.")
    if contact.guardian_activated_at is not None or not contact.guardian_activation_pin_hash:
        raise HTTPException(status_code=409, detail="This guardian activation PIN is unavailable or has already been used.")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if contact.guardian_activation_expires_at and contact.guardian_activation_expires_at < now:
        raise HTTPException(status_code=400, detail="Guardian activation PIN has expired. Contact the school.")
    if not verify_pin(payload.pin, contact.guardian_activation_pin_hash):
        raise HTTPException(status_code=400, detail="Invalid guardian activation PIN")

    profile = db.get(Profile, identity["id"])
    if profile is None:
        profile = Profile(id=identity["id"], role="pending", is_active=False)
        db.add(profile)
        db.flush()

    user = None
    if profile.local_user_id is not None:
        user = db.get(User, profile.local_user_id)
        if (
            user is None or not user.is_active or not profile.is_active or profile.role != "parent"
            or profile.school_id != school.id or user.role != "parent"
        ):
            raise HTTPException(status_code=409, detail="This identity is already linked to a different Chikoro role or school.")
    else:
        if profile.is_active or profile.role not in ("pending", "parent"):
            raise HTTPException(status_code=409, detail="This Supabase identity is not eligible for guardian activation.")
        if db.query(User).filter(User.email == email).first():
            raise HTTPException(status_code=409, detail="This email is already linked to a local account. Contact the school administrator.")
        user = User(
            email=email,
            full_name=contact.name,
            password_hash=hash_password("supabase-managed-" + identity["id"]),
            role="parent",
            school_id=school.id,
            is_active=True,
        )
        db.add(user)
        db.flush()
        profile.local_user_id = user.id
        profile.role = "parent"
        profile.school_id = school.id
        profile.is_active = True
        profile.updated_at = now

    existing_link = db.query(GuardianLink).filter(
        GuardianLink.profile_id == identity["id"],
        GuardianLink.contact_id == contact.id,
    ).first()
    if existing_link is not None:
        raise HTTPException(status_code=409, detail="This guardian relationship is already linked.")

    link = GuardianLink(
        profile_id=identity["id"],
        contact_id=contact.id,
        school_id=school.id,
        is_active=True,
        verified_at=now,
    )
    db.add(link)
    contact.verified_email = True
    contact.guardian_activated_at = now
    contact.guardian_activation_pin_hash = None
    contact.guardian_activation_expires_at = None
    db.commit()
    write_audit(db, user.id, "guardian.register", "contact", contact.id, {"student_id": contact.student_id}, school_id=school.id)
    return {"status": "activated", "email": email, "student_id": contact.student_id, "school_code": school.code}


@router.get("/fee-status")
def portal_fee_status(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    if principal.role == "student":
        student = db.query(Student).filter(Student.portal_user_id == principal.user_id).first()
        if student is None:
            raise HTTPException(status_code=404, detail="No learner record is linked to this account")
        invoices = _invoice_items(db, student)
        total_balance = student_balance(db, student.school_id, student.id)
        return {
            "role": "student",
            "student_number": student.student_number,
            "name": f"{student.first_name} {student.last_name}",
            "invoices": invoices,
            "total_balance": float(total_balance),
        }

    if principal.role == "parent":
        links = db.query(GuardianLink, Contact, Student).join(
            Contact, Contact.id == GuardianLink.contact_id
        ).join(
            Student, Student.id == Contact.student_id
        ).filter(
            GuardianLink.profile_id == principal.auth_user_id,
            GuardianLink.school_id == principal.school_id,
            GuardianLink.is_active.is_(True),
            Contact.school_id == principal.school_id,
        ).order_by(Student.last_name, Student.first_name).all()
        children = []
        for _link, _contact, student in links:
            children.append({
                "student_id": student.id,
                "student_number": student.student_number,
                "name": f"{student.first_name} {student.last_name}",
                "invoices": _invoice_items(db, student),
                "total_balance": float(student_balance(db, student.school_id, student.id)),
            })
        if not children:
            raise HTTPException(status_code=404, detail="No verified learner relationships are linked to this guardian account")
        return {"role": "parent", "name": (db.get(User, principal.user_id).full_name), "children": children}

    raise HTTPException(status_code=403, detail="Student or parent portal access required")


@router.get("/me")
def portal_me(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    user = db.get(User, principal.user_id)
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": principal.role, "school_id": principal.school_id}
