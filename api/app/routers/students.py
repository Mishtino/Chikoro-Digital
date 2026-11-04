import secrets
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from sqlalchemy import text, func

from app.database import get_db
from app.deps_supabase import SupabasePrincipal, require_supabase_roles
from app.models.student import Student, Contact
from app.models.school import School
from app.models.user import User
from app.services.auth import hash_password
from app.services.ids import generate_student_number, generate_pin, hash_pin
from app.services.audit import write_audit

router = APIRouter(prefix="/students", tags=["students"])


class StudentCreate(BaseModel):
    first_name: str
    last_name: str
    form: Optional[str] = None
    guardian_name: Optional[str] = None
    guardian_phone: Optional[str] = None
    guardian_email: Optional[str] = None
    student_email: Optional[str] = None
    school_id: Optional[int] = None


class StudentOut(BaseModel):
    id: int
    school_id: int
    student_number: str
    first_name: str
    last_name: str
    form: Optional[str] = None
    status: str
    activated: bool

    model_config = ConfigDict(from_attributes=True)


class StudentCreateResult(StudentOut):
    pin: str
    guardian_contact_id: Optional[int] = None
    portal_email: Optional[str] = None


def _school_id(principal: SupabasePrincipal, requested: Optional[int]) -> int:
    if principal.is_admin:
        if requested is None:
            raise HTTPException(status_code=400, detail="school_id required for admin")
        return requested
    if principal.school_id is None:
        raise HTTPException(status_code=403, detail="School context required")
    return principal.school_id


@router.post("", response_model=StudentCreateResult, status_code=status.HTTP_201_CREATED)
def create_student(payload: StudentCreate, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar', 'teacher')), db: Session = Depends(get_db)):
    sid = _school_id(principal, payload.school_id)
    school = db.get(School, sid)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")

    portal_email = payload.student_email.strip().lower() if payload.student_email else None
    guardian_email = payload.guardian_email.strip().lower() if payload.guardian_email else None
    if guardian_email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", guardian_email):
        raise HTTPException(status_code=422, detail="Guardian email address is invalid")
    if portal_email:
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", portal_email):
            raise HTTPException(status_code=422, detail="Student email address is invalid")
        if db.query(User).filter(func.lower(User.email) == portal_email).first():
            raise HTTPException(status_code=409, detail="Student email is already assigned to another account")

    count = db.query(Student).filter(Student.school_id == sid).count()
    number = generate_student_number(school.code, count + 1)
    pin = generate_pin(8)
    student = Student(
        school_id=sid,
        student_number=number,
        first_name=payload.first_name,
        last_name=payload.last_name,
        form=payload.form,
        activation_pin_hash=hash_pin(pin),
        activation_expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
    )
    db.add(student)
    db.flush()

    if portal_email:
        portal_user = User(
            email=portal_email,
            full_name=f"{student.first_name} {student.last_name}",
            password_hash=hash_password(secrets.token_urlsafe(48)),
            role="student",
            school_id=sid,
            is_active=True,
            is_admin=False,
        )
        db.add(portal_user)
        db.flush()
        student.portal_user_id = portal_user.id

    guardian_contact_id = None
    if payload.guardian_name or payload.guardian_phone or payload.guardian_email:
        contact = Contact(
            school_id=sid,
            student_id=student.id,
            name=payload.guardian_name or "Guardian",
            phone=payload.guardian_phone,
            email=guardian_email,
            is_primary=True,
        )
        db.add(contact)
        db.flush()
        guardian_contact_id = contact.id

    db.commit()
    db.refresh(student)
    write_audit(db, principal, "student.create", "student", student.id, {"number": number, "portal_enabled": bool(portal_email)}, school_id=sid)
    return StudentCreateResult(
        id=student.id,
        school_id=student.school_id,
        student_number=student.student_number,
        first_name=student.first_name,
        last_name=student.last_name,
        form=student.form,
        status=student.status,
        activated=bool(student.activated_at),
        pin=pin,
        guardian_contact_id=guardian_contact_id,
        portal_email=portal_email,
    )


@router.post("/{student_id}/guardians/{contact_id}/activation-pin")
def issue_guardian_activation_pin(student_id: int, contact_id: int, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster')), db: Session = Depends(get_db)):
    sid = principal.school_id
    if sid is None or principal.is_admin:
        raise HTTPException(status_code=403, detail="School-scoped administrator access required")
    student = db.query(Student).filter(Student.id == student_id, Student.school_id == sid).first()
    contact = db.query(Contact).filter(Contact.id == contact_id, Contact.student_id == student_id, Contact.school_id == sid).first()
    if student is None or contact is None:
        raise HTTPException(status_code=404, detail="Student guardian contact not found")
    if not contact.email:
        raise HTTPException(status_code=422, detail="Guardian email is required for online activation")
    activated = db.execute(text("SELECT guardian_activated_at FROM public.contacts WHERE id=:id AND school_id=:school_id"), {"id": contact_id, "school_id": sid}).scalar_one_or_none()
    if activated is not None:
        raise HTTPException(status_code=409, detail="Guardian contact is already activated")
    pin = generate_pin(8)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)
    db.execute(text("UPDATE public.contacts SET guardian_activation_pin_hash=:pin_hash, guardian_activation_expires_at=:expires_at WHERE id=:id AND student_id=:student_id AND school_id=:school_id"), {"pin_hash": hash_pin(pin), "expires_at": expires_at, "id": contact_id, "student_id": student_id, "school_id": sid})
    db.commit()
    write_audit(db, principal, "guardian.activation.pin.issue", "guardian_contact", contact_id, {"expires_at": expires_at.isoformat()}, school_id=sid)
    return {"activation_pin": pin, "expires_at": expires_at.isoformat()}


@router.get("", response_model=List[StudentOut])
def list_students(school_id: Optional[int] = Query(None), principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar', 'teacher')), db: Session = Depends(get_db)):
    sid = _school_id(principal, school_id) if (principal.is_admin or school_id is not None) else principal.school_id
    if sid is None:
        raise HTTPException(status_code=403, detail="School context required")
    students = db.query(Student).filter(Student.school_id == sid).order_by(Student.id).all()
    return [
        StudentOut(
            id=s.id,
            school_id=s.school_id,
            student_number=s.student_number,
            first_name=s.first_name,
            last_name=s.last_name,
            form=s.form,
            status=s.status,
            activated=bool(s.activated_at),
        )
        for s in students
    ]


@router.get("/{student_id}")
def get_student(student_id: int, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar', 'teacher')), db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    if not principal.is_admin and principal.school_id != student.school_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return {
        "id": student.id,
        "school_id": student.school_id,
        "student_number": student.student_number,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "form": student.form,
        "status": student.status,
        "activated": bool(student.activated_at),
    }
