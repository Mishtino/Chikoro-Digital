from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps_supabase import SupabasePrincipal, require_supabase_roles
from app.models.attendance import AttendanceSession, AttendanceRecord
from app.models.fee import Term
from app.models.student import Student
from app.services.audit import write_audit
from app.services.class_access import assigned_class_names, require_teacher_class

router = APIRouter(prefix="/attendance", tags=["attendance"])
SCHOOL_ROLES = ("owner", "headmaster", "teacher")
RECORD_STATES = {"present", "absent", "late", "excused"}


def _school(principal: SupabasePrincipal, requested: Optional[int]) -> int:
    if principal.is_admin or principal.role not in SCHOOL_ROLES or principal.school_id is None:
        raise HTTPException(status_code=403, detail="School attendance access required")
    if requested is not None and requested != principal.school_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return principal.school_id


class SessionCreate(BaseModel):
    class_name: str = Field(min_length=1, max_length=40)
    attendance_date: date
    term_id: Optional[int] = None

    @field_validator("class_name")
    @classmethod
    def normalize_class(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Class name is required")
        return value


class AttendanceEntry(BaseModel):
    student_id: int
    status: str
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value):
        value = value.strip().lower()
        if value not in RECORD_STATES:
            raise ValueError("Attendance status must be present, absent, late or excused")
        return value

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value):
        if value is None:
            return None
        return value.strip() or None


class BulkAttendance(BaseModel):
    entries: List[AttendanceEntry] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_students(self):
        ids = [entry.student_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("A learner may appear only once in an attendance submission")
        return self


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreate,
    principal: SupabasePrincipal = Depends(require_supabase_roles(*SCHOOL_ROLES)),
    db: Session = Depends(get_db),
):
    school_id = _school(principal, None)
    require_teacher_class(db, principal, school_id, payload.class_name)
    if payload.term_id is not None and db.query(Term).filter(
        Term.id == payload.term_id, Term.school_id == school_id
    ).first() is None:
        raise HTTPException(status_code=404, detail="Academic term not found in this school")
    session = AttendanceSession(
        school_id=school_id,
        term_id=payload.term_id,
        class_name=payload.class_name,
        attendance_date=payload.attendance_date,
        recorded_by_user_id=principal.user_id,
    )
    db.add(session)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An attendance register already exists for this class and date")
    db.refresh(session)
    write_audit(db, principal, "attendance.session.create", "attendance_session", session.id, {
        "class_name": session.class_name, "attendance_date": session.attendance_date.isoformat(),
    }, school_id=school_id)
    return {
        "id": session.id, "class_name": session.class_name,
        "attendance_date": session.attendance_date.isoformat(),
        "term_id": session.term_id, "status": session.status,
        "recorded_by_user_id": session.recorded_by_user_id,
    }


@router.get("/sessions")
def list_sessions(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    class_name: Optional[str] = Query(None, max_length=40),
    school_id: Optional[int] = Query(None),
    principal: SupabasePrincipal = Depends(require_supabase_roles(*SCHOOL_ROLES)),
    db: Session = Depends(get_db),
):
    sid = _school(principal, school_id)
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=422, detail="from_date must be on or before to_date")
    query = db.query(AttendanceSession).filter(AttendanceSession.school_id == sid)
    if principal.role == "teacher" and not principal.is_admin:
        allowed_classes = assigned_class_names(db, principal, sid) or set()
        if not allowed_classes:
            return []
        query = query.filter(AttendanceSession.class_name.in_(allowed_classes))
    if from_date:
        query = query.filter(AttendanceSession.attendance_date >= from_date)
    if to_date:
        query = query.filter(AttendanceSession.attendance_date <= to_date)
    if class_name:
        query = query.filter(AttendanceSession.class_name == class_name.strip())
    sessions = query.order_by(AttendanceSession.attendance_date.desc(), AttendanceSession.id.desc()).limit(200).all()
    result = []
    for session in sessions:
        records = db.query(AttendanceRecord).filter(
            AttendanceRecord.school_id == sid, AttendanceRecord.session_id == session.id
        ).all()
        counts = {state: 0 for state in RECORD_STATES}
        for record in records:
            counts[record.status] += 1
        result.append({
            "id": session.id, "class_name": session.class_name,
            "attendance_date": session.attendance_date.isoformat(),
            "term_id": session.term_id, "status": session.status,
            "recorded_by_user_id": session.recorded_by_user_id,
            "record_count": len(records), "counts": counts,
        })
    return result


@router.get("/sessions/{session_id}/records")
def get_session_records(
    session_id: int,
    principal: SupabasePrincipal = Depends(require_supabase_roles(*SCHOOL_ROLES)),
    db: Session = Depends(get_db),
):
    sid = _school(principal, None)
    session = db.query(AttendanceSession).filter(
        AttendanceSession.id == session_id, AttendanceSession.school_id == sid
    ).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Attendance register not found")
    require_teacher_class(db, principal, sid, session.class_name)
    students = db.query(Student).filter(
        Student.school_id == sid, Student.form == session.class_name, Student.status == "active"
    ).order_by(Student.last_name, Student.first_name).all()
    records = {
        row.student_id: row
        for row in db.query(AttendanceRecord).filter(
            AttendanceRecord.school_id == sid, AttendanceRecord.session_id == session.id
        ).all()
    }
    return {
        "session": {
            "id": session.id, "class_name": session.class_name,
            "attendance_date": session.attendance_date.isoformat(), "status": session.status,
            "term_id": session.term_id,
        },
        "students": [{
            "student_id": student.id, "student_number": student.student_number,
            "first_name": student.first_name, "last_name": student.last_name,
            "status": records[student.id].status if student.id in records else None,
            "note": records[student.id].note if student.id in records else None,
        } for student in students],
    }


@router.put("/sessions/{session_id}/records")
def save_session_records(
    session_id: int,
    payload: BulkAttendance,
    principal: SupabasePrincipal = Depends(require_supabase_roles(*SCHOOL_ROLES)),
    db: Session = Depends(get_db),
):
    sid = _school(principal, None)
    session = db.query(AttendanceSession).filter(
        AttendanceSession.id == session_id, AttendanceSession.school_id == sid
    ).with_for_update().first()
    if session is None:
        raise HTTPException(status_code=404, detail="Attendance register not found")
    require_teacher_class(db, principal, sid, session.class_name)
    if session.status != "draft":
        raise HTTPException(status_code=409, detail="Submitted attendance registers are read-only")
    student_ids = sorted(entry.student_id for entry in payload.entries)
    students = db.query(Student).filter(
        Student.id.in_(student_ids), Student.school_id == sid,
        Student.form == session.class_name, Student.status == "active",
    ).all()
    if len(students) != len(student_ids):
        raise HTTPException(status_code=422, detail="Every learner must be active and belong to this school's selected class")
    existing = {
        row.student_id: row
        for row in db.query(AttendanceRecord).filter(
            AttendanceRecord.school_id == sid, AttendanceRecord.session_id == session.id,
            AttendanceRecord.student_id.in_(student_ids),
        ).with_for_update().all()
    }
    for entry in payload.entries:
        row = existing.get(entry.student_id)
        if row is None:
            row = AttendanceRecord(
                school_id=sid, session_id=session.id, student_id=entry.student_id,
                status=entry.status, note=entry.note, marked_by_user_id=principal.user_id,
            )
            db.add(row)
        else:
            row.status = entry.status
            row.note = entry.note
            row.marked_by_user_id = principal.user_id
    db.flush()
    write_audit(db, principal, "attendance.records.save", "attendance_session", session.id, {
        "count": len(payload.entries),
    }, school_id=sid)
    return {"saved": len(payload.entries)}


@router.post("/sessions/{session_id}/submit")
def submit_session(
    session_id: int,
    principal: SupabasePrincipal = Depends(require_supabase_roles(*SCHOOL_ROLES)),
    db: Session = Depends(get_db),
):
    sid = _school(principal, None)
    session = db.query(AttendanceSession).filter(
        AttendanceSession.id == session_id, AttendanceSession.school_id == sid
    ).with_for_update().first()
    if session is None:
        raise HTTPException(status_code=404, detail="Attendance register not found")
    require_teacher_class(db, principal, sid, session.class_name)
    if session.status != "draft":
        raise HTTPException(status_code=409, detail="Attendance register has already been submitted")
    roster = db.query(Student.id).filter(
        Student.school_id == sid, Student.form == session.class_name, Student.status == "active"
    ).all()
    marked = db.query(AttendanceRecord.student_id).filter(
        AttendanceRecord.school_id == sid, AttendanceRecord.session_id == session.id
    ).all()
    marked_ids = {row[0] for row in marked}
    missing = [row[0] for row in roster if row[0] not in marked_ids]
    if missing:
        raise HTTPException(status_code=409, detail=f"{len(missing)} active learner(s) still need an attendance status")
    if not roster:
        raise HTTPException(status_code=409, detail="This class has no active learners")
    session.status = "submitted"
    session.submitted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.flush()
    write_audit(db, principal, "attendance.session.submit", "attendance_session", session.id, {
        "learner_count": len(roster),
    }, school_id=sid)
    return {"submitted": True, "learner_count": len(roster)}
