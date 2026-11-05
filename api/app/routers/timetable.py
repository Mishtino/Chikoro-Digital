from datetime import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps_supabase import SupabasePrincipal, require_supabase_roles
from app.models.fee import Term
from app.models.results import Subject
from app.models.school import School
from app.models.timetable import TimetableEntry
from app.models.user import User
from app.services.audit import write_audit
from app.services.class_access import assigned_class_names

router = APIRouter(prefix="/timetable", tags=["timetable"])
SCHOOL_ROLES = ("owner", "headmaster", "teacher")


def _school(principal: SupabasePrincipal, requested: Optional[int]) -> int:
    if principal.is_admin or principal.role not in SCHOOL_ROLES or principal.school_id is None:
        raise HTTPException(status_code=403, detail="School timetable access required")
    if requested is not None and requested != principal.school_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return principal.school_id


class TimetableCreate(BaseModel):
    term_id: int
    subject_id: int
    teacher_user_id: Optional[int] = None
    class_name: str = Field(min_length=1, max_length=40)
    day_of_week: int = Field(ge=1, le=7)
    period_number: int = Field(ge=1, le=20)
    start_time: time
    end_time: time
    room: Optional[str] = Field(default=None, max_length=80)

    @field_validator("class_name", "room")
    @classmethod
    def normalize_text(cls, value):
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_period(self):
        if self.start_time >= self.end_time:
            raise ValueError("Period end time must be later than start time")
        if not self.class_name:
            raise ValueError("Class name is required")
        return self


@router.get("/entries")
def list_timetable_entries(
    class_name: Optional[str] = Query(None, max_length=40),
    day_of_week: Optional[int] = Query(None, ge=1, le=7),
    term_id: Optional[int] = Query(None),
    school_id: Optional[int] = Query(None),
    principal: SupabasePrincipal = Depends(require_supabase_roles(*SCHOOL_ROLES)),
    db: Session = Depends(get_db),
):
    sid = _school(principal, school_id)
    query = (
        db.query(TimetableEntry, Subject, User)
        .join(Subject, and_(Subject.id == TimetableEntry.subject_id, Subject.school_id == sid))
        .outerjoin(User, and_(User.id == TimetableEntry.teacher_user_id, User.school_id == sid))
        .filter(TimetableEntry.school_id == sid)
    )
    if principal.role == "teacher" and not principal.is_admin:
        allowed_classes = assigned_class_names(db, principal, sid) or set()
        query = query.filter(or_(TimetableEntry.class_name.in_(allowed_classes), TimetableEntry.teacher_user_id == principal.user_id))
    if class_name:
        query = query.filter(TimetableEntry.class_name == class_name.strip())
    if day_of_week is not None:
        query = query.filter(TimetableEntry.day_of_week == day_of_week)
    if term_id is not None:
        if db.query(Term).filter(Term.id == term_id, Term.school_id == sid).first() is None:
            raise HTTPException(status_code=404, detail="Academic term not found in this school")
        query = query.filter(TimetableEntry.term_id == term_id)
    rows = query.order_by(
        TimetableEntry.day_of_week, TimetableEntry.period_number, TimetableEntry.start_time
    ).limit(1000).all()
    return [{
        "id": entry.id, "class_name": entry.class_name,
        "day_of_week": entry.day_of_week, "period_number": entry.period_number,
        "start_time": entry.start_time.strftime("%H:%M"),
        "end_time": entry.end_time.strftime("%H:%M"), "room": entry.room,
        "term_id": entry.term_id, "subject_id": subject.id, "subject_name": subject.name,
        "teacher_user_id": teacher.id if teacher else None,
        "teacher_name": teacher.full_name if teacher else None,
    } for entry, subject, teacher in rows]


@router.post("/entries", status_code=status.HTTP_201_CREATED)
def create_timetable_entry(
    payload: TimetableCreate,
    principal: SupabasePrincipal = Depends(require_supabase_roles("owner", "headmaster")),
    db: Session = Depends(get_db),
):
    sid = _school(principal, None)
    school = db.query(School).filter(School.id == sid).with_for_update().first()
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    if db.query(Term).filter(Term.id == payload.term_id, Term.school_id == sid).first() is None:
        raise HTTPException(status_code=404, detail="Academic term not found in this school")
    if db.query(Subject).filter(Subject.id == payload.subject_id, Subject.school_id == sid).first() is None:
        raise HTTPException(status_code=404, detail="Subject not found in this school")
    if payload.teacher_user_id is not None:
        teacher = db.query(User).filter(
            User.id == payload.teacher_user_id, User.school_id == sid,
            User.role == "teacher", User.is_active.is_(True), User.is_admin.is_(False),
        ).first()
        if teacher is None:
            raise HTTPException(status_code=404, detail="Active teacher not found in this school")

    overlap = and_(
        TimetableEntry.school_id == sid,
        TimetableEntry.term_id == payload.term_id,
        TimetableEntry.day_of_week == payload.day_of_week,
        TimetableEntry.start_time < payload.end_time,
        TimetableEntry.end_time > payload.start_time,
    )
    conflicts = db.query(TimetableEntry).filter(
        overlap,
        or_(
            TimetableEntry.class_name == payload.class_name,
            and_(payload.teacher_user_id is not None, TimetableEntry.teacher_user_id == payload.teacher_user_id),
            and_(payload.room is not None, TimetableEntry.room == payload.room),
        ),
    ).first()
    if conflicts:
        raise HTTPException(status_code=409, detail="This class, teacher or room already has a timetable entry during that time")

    entry = TimetableEntry(
        school_id=sid, term_id=payload.term_id, subject_id=payload.subject_id,
        teacher_user_id=payload.teacher_user_id, class_name=payload.class_name,
        day_of_week=payload.day_of_week, period_number=payload.period_number,
        start_time=payload.start_time, end_time=payload.end_time, room=payload.room,
        created_by_user_id=principal.user_id,
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A timetable period already exists for this class")
    db.refresh(entry)
    write_audit(db, principal, "timetable.entry.create", "timetable_entry", entry.id, {
        "class_name": entry.class_name, "day_of_week": entry.day_of_week,
        "period_number": entry.period_number, "subject_id": entry.subject_id,
    }, school_id=sid)
    return {"id": entry.id}


@router.delete("/entries/{entry_id}")
def delete_timetable_entry(
    entry_id: int,
    principal: SupabasePrincipal = Depends(require_supabase_roles("owner", "headmaster")),
    db: Session = Depends(get_db),
):
    sid = _school(principal, None)
    entry = db.query(TimetableEntry).filter(
        TimetableEntry.id == entry_id, TimetableEntry.school_id == sid
    ).with_for_update().first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Timetable entry not found")
    details = {
        "class_name": entry.class_name, "day_of_week": entry.day_of_week,
        "period_number": entry.period_number, "subject_id": entry.subject_id,
    }
    db.delete(entry)
    db.commit()
    write_audit(db, principal, "timetable.entry.delete", "timetable_entry", entry_id, details, school_id=sid)
    return {"deleted": True}
