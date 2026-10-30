import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_principal, Principal
from app.models.student import Student, Contact
from app.models.school import School
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

    class Config:
        from_attributes = True


class StudentCreateResult(StudentOut):
    pin: str


def _school_id(principal: Principal, requested: Optional[int]) -> int:
    if principal.is_admin:
        if requested is None:
            raise HTTPException(status_code=400, detail="school_id required for admin")
        return requested
    if principal.school_id is None:
        raise HTTPException(status_code=403, detail="School context required")
    return principal.school_id


@router.post("", response_model=StudentCreateResult, status_code=status.HTTP_201_CREATED)
def create_student(payload: StudentCreate, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    sid = _school_id(principal, payload.school_id)
    school = db.get(School, sid)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    # sequence
    count = db.query(Student).filter(Student.school_id == sid).count()
    number = generate_student_number(school.code, count + 1)
    pin = generate_pin()
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
    db.commit()
    db.refresh(student)
    if payload.guardian_name or payload.guardian_phone or payload.guardian_email:
        contact = Contact(
            school_id=sid,
            student_id=student.id,
            name=payload.guardian_name or "Guardian",
            phone=payload.guardian_phone,
            email=payload.guardian_email,
            is_primary=True,
        )
        db.add(contact)
        db.commit()
    write_audit(db, principal, "student.create", "student", student.id, {"number": number}, school_id=sid)
    result = StudentCreateResult(
        id=student.id,
        school_id=student.school_id,
        student_number=student.student_number,
        first_name=student.first_name,
        last_name=student.last_name,
        form=student.form,
        status=student.status,
        activated=bool(student.activated_at),
        pin=pin,
    )
    return result


@router.get("", response_model=List[StudentOut])
def list_students(school_id: Optional[int] = Query(None), principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
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
def get_student(student_id: int, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
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
