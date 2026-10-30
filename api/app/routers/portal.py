from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_principal, Principal
from app.models.school import School
from app.models.student import Student, Contact
from app.models.payment import Invoice
from app.services.auth import hash_password
from app.services.ids import verify_pin
from app.services.money import invoice_balance, student_balance
from app.services.audit import write_audit

router = APIRouter(prefix="/portal", tags=["portal"])


class PortalRegisterRequest(BaseModel):
    school_code: str
    student_number: str
    pin: str
    password: str
    email: Optional[str] = None
    phone: Optional[str] = None


class PortalFeeItem(BaseModel):
    invoice_number: str
    total: float
    balance: float
    currency: str
    issued_at: Optional[str] = None


@router.post("/register", status_code=status.HTTP_201_CREATED)
def portal_register(payload: PortalRegisterRequest, db: Session = Depends(get_db)):
    school = db.query(School).filter(School.code == payload.school_code).first()
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    student = db.query(Student).filter(Student.school_id == school.id, Student.student_number == payload.student_number).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    if student.activated_at is not None:
        raise HTTPException(status_code=400, detail="Student already activated")
    if student.activation_pin_hash is None:
        raise HTTPException(status_code=400, detail="No active PIN")
    if student.activation_expires_at is not None and student.activation_expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="PIN expired")
    if not verify_pin(payload.pin, student.activation_pin_hash):
        raise HTTPException(status_code=400, detail="Invalid PIN")
    # unique email
    email = payload.email or f"{student.student_number}@students.chikoro"
    from app.models.user import User
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=email,
        full_name=f"{student.first_name} {student.last_name}",
        password_hash=hash_password(payload.password),
        role="student",
        school_id=school.id,
        is_active=True,
    )
    db.add(user)
    db.flush()
    student.portal_user_id = user.id
    student.activated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    student.activation_pin_hash = None
    if payload.phone:
        contact = Contact(school_id=school.id, student_id=student.id, name="Self", phone=payload.phone, is_primary=True)
        db.add(contact)
    db.commit()
    write_audit(db, user.id, "portal.register", "student", student.id, {"email": payload.email}, school_id=school.id)
    return {"status": "registered", "email": payload.email}


@router.get("/fee-status")
def portal_fee_status(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    if principal.role not in ("student", "parent", "admin"):
        raise HTTPException(status_code=403, detail="Portal users only")
    from app.models.user import User
    # find student linked to this user
    student = db.query(Student).filter(Student.portal_user_id == principal.user_id).first()
    if student is None and not principal.is_admin:
        raise HTTPException(status_code=404, detail="No student linked")
    if student is None:
        raise HTTPException(status_code=400, detail="student context required")
    invoices = db.query(Invoice).filter(Invoice.school_id == student.school_id, Invoice.student_id == student.id).order_by(Invoice.id).all()
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
    from app.models.user import User
    user = db.get(User, principal.user_id)
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role, "school_id": user.school_id}
