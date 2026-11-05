from typing import List, Optional
import math

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps_supabase import SupabasePrincipal, require_supabase_roles
from app.models.results import Subject, Assessment, Mark
from app.models.student import Student
from app.models.fee import Term
from app.services.audit import write_audit
from app.services.class_access import require_teacher_class

router = APIRouter(prefix="/results", tags=["results"])


class SubjectCreate(BaseModel):
    name: str
    code: Optional[str] = None
    school_id: Optional[int] = None


class AssessmentCreate(BaseModel):
    subject_id: int
    term_id: Optional[int] = None
    name: str
    weight: float = 1.0
    max_score: float = 100.0
    school_id: Optional[int] = None


class MarkEntry(BaseModel):
    student_id: int
    assessment_id: int
    score: float


class BulkMarksRequest(BaseModel):
    entries: List[MarkEntry]
    school_id: Optional[int] = None


def _sid(principal: SupabasePrincipal, requested: Optional[int]) -> int:
    if principal.is_admin:
        if requested is None:
            raise HTTPException(status_code=400, detail="school_id required")
        return requested
    if principal.school_id is None:
        raise HTTPException(status_code=403, detail="School context required")
    if requested is not None and requested != principal.school_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return principal.school_id


@router.post("/subjects", status_code=status.HTTP_201_CREATED)
def create_subject(payload: SubjectCreate, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'teacher')), db: Session = Depends(get_db)):
    sid = _sid(principal, payload.school_id)
    subject = Subject(school_id=sid, name=payload.name, code=payload.code)
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return {"id": subject.id, "name": subject.name, "code": subject.code}


@router.get("/subjects")
def list_subjects(school_id: Optional[int] = Query(None), principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'teacher')), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id) if (principal.is_admin or school_id is not None) else principal.school_id
    if sid is None:
        raise HTTPException(status_code=403, detail="School context required")
    return db.query(Subject).filter(Subject.school_id == sid).order_by(Subject.id).all()


@router.post("/assessments", status_code=status.HTTP_201_CREATED)
def create_assessment(payload: AssessmentCreate, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'teacher')), db: Session = Depends(get_db)):
    sid = _sid(principal, payload.school_id)
    subject = db.query(Subject).filter(Subject.id == payload.subject_id, Subject.school_id == sid).first()
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found in this school")
    if payload.term_id is not None and db.query(Term).filter(Term.id == payload.term_id, Term.school_id == sid).first() is None:
        raise HTTPException(status_code=404, detail="Term not found in this school")
    if not math.isfinite(payload.max_score) or not math.isfinite(payload.weight) or payload.max_score <= 0 or payload.weight <= 0:
        raise HTTPException(status_code=422, detail="Assessment weight and maximum score must be finite positive values")
    a = Assessment(school_id=sid, subject_id=payload.subject_id, term_id=payload.term_id, name=payload.name, weight=payload.weight, max_score=payload.max_score)
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"id": a.id}


@router.get("/assessments")
def list_assessments(subject_id: Optional[int] = Query(None), term_id: Optional[int] = Query(None), school_id: Optional[int] = Query(None), principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'teacher')), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id) if (principal.is_admin or school_id is not None) else principal.school_id
    if sid is None:
        raise HTTPException(status_code=403, detail="School context required")
    q = db.query(Assessment).filter(Assessment.school_id == sid)
    if subject_id is not None:
        q = q.filter(Assessment.subject_id == subject_id)
    if term_id is not None:
        if db.query(Term).filter(Term.id == term_id, Term.school_id == sid).first() is None:
            raise HTTPException(status_code=404, detail="Term not found in this school")
        q = q.filter(Assessment.term_id == term_id)
    return q.order_by(Assessment.id).all()


@router.post("/marks")
def enter_marks(payload: BulkMarksRequest, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'teacher')), db: Session = Depends(get_db)):
    sid = _sid(principal, payload.school_id)
    submitted_pairs = [(entry.student_id, entry.assessment_id) for entry in payload.entries]
    if len(submitted_pairs) != len(set(submitted_pairs)):
        raise HTTPException(
            status_code=422,
            detail="A learner can only have one mark per assessment in a single bulk request",
        )

    # Lock assessment rows in a stable order so concurrent bulk submissions
    # for the same assessment serialize before checking/inserting marks.
    assessment_ids = sorted({entry.assessment_id for entry in payload.entries})
    locked_assessments = (
        db.query(Assessment)
        .filter(Assessment.school_id == sid, Assessment.id.in_(assessment_ids))
        .order_by(Assessment.id)
        .with_for_update()
        .all()
    )
    assessments_by_id = {assessment.id: assessment for assessment in locked_assessments}
    if len(assessments_by_id) != len(assessment_ids):
        raise HTTPException(status_code=404, detail="Assessment not found in this school")

    created = 0
    for e in payload.entries:
        student = db.query(Student).filter(Student.id == e.student_id, Student.school_id == sid).first()
        assessment = assessments_by_id.get(e.assessment_id)
        if student is None:
            raise HTTPException(status_code=404, detail="Student or assessment not found in this school")
        if principal.role == "teacher" and not principal.is_admin:
            require_teacher_class(db, principal, sid, student.form or "")
        if not math.isfinite(e.score) or e.score < 0 or e.score > assessment.max_score:
            raise HTTPException(status_code=422, detail="Mark score must be finite and within the assessment range")
        existing = db.query(Mark).filter(Mark.school_id == sid, Mark.student_id == e.student_id, Mark.assessment_id == e.assessment_id).first()
        if existing:
            if existing.status != "draft":
                raise HTTPException(status_code=409, detail="Approved or published marks cannot be edited")
            existing.score = e.score
            existing.entered_by_user_id = principal.user_id
        else:
            db.add(Mark(school_id=sid, student_id=e.student_id, assessment_id=e.assessment_id, score=e.score, entered_by_user_id=principal.user_id))
        created += 1
    db.commit()
    write_audit(db, principal, "marks.enter", "assessment", None, {"count": created}, school_id=sid)
    return {"saved": created}



@router.get("/marks")
def list_marks(
    assessment_id: Optional[int] = Query(None),
    term_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    school_id: Optional[int] = Query(None),
    principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'teacher')),
    db: Session = Depends(get_db),
):
    if principal.is_admin or principal.role not in {"owner", "headmaster", "teacher"}:
        raise HTTPException(status_code=403, detail="School academic access required")
    sid = _sid(principal, school_id) if (principal.is_admin or school_id is not None) else principal.school_id
    if sid is None:
        raise HTTPException(status_code=403, detail="School context required")
    if status_filter is not None and status_filter not in {"draft", "approved", "published"}:
        raise HTTPException(status_code=422, detail="Invalid mark status")
    if term_id is not None and db.query(Term).filter(Term.id == term_id, Term.school_id == sid).first() is None:
        raise HTTPException(status_code=404, detail="Term not found in this school")

    query = (
        db.query(Mark, Student, Assessment, Subject)
        .join(Student, Student.id == Mark.student_id)
        .join(Assessment, Assessment.id == Mark.assessment_id)
        .join(Subject, Subject.id == Assessment.subject_id)
        .filter(
            Mark.school_id == sid,
            Student.school_id == sid,
            Assessment.school_id == sid,
            Subject.school_id == sid,
        )
    )
    if assessment_id is not None:
        query = query.filter(Mark.assessment_id == assessment_id)
    if term_id is not None:
        query = query.filter(Assessment.term_id == term_id)
    if status_filter is not None:
        query = query.filter(Mark.status == status_filter)
    if principal.role == "teacher" and not principal.is_admin:
        query = query.filter(Mark.entered_by_user_id == principal.user_id)

    rows = query.order_by(Mark.id.desc()).limit(1000).all()
    return [
        {
            "id": mark.id,
            "student_id": student.id,
            "student_number": student.student_number,
            "student_name": f"{student.first_name} {student.last_name}",
            "assessment_id": assessment.id,
            "assessment_name": assessment.name,
            "subject_name": subject.name,
            "term_id": assessment.term_id,
            "score": float(mark.score),
            "max_score": float(assessment.max_score),
            "status": mark.status,
            "published_at": mark.published_at.isoformat() if mark.published_at else None,
        }
        for mark, student, assessment, subject in rows
    ]


@router.post("/marks/approve")
def approve_marks(assessment_id: int, school_id: Optional[int] = None, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster')), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id)
    if db.query(Assessment).filter(Assessment.id == assessment_id, Assessment.school_id == sid).first() is None:
        raise HTTPException(status_code=404, detail="Assessment not found in this school")
    updated = db.query(Mark).filter(Mark.school_id == sid, Mark.assessment_id == assessment_id, Mark.status == "draft").update({"status": "approved"})
    db.commit()
    write_audit(db, principal, "marks.approve", "assessment", assessment_id, {"count": updated}, school_id=sid)
    return {"approved": updated}
@router.post("/marks/publish")
def publish_marks(assessment_id: int, school_id: Optional[int] = None, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster')), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id)
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id, Assessment.school_id == sid).first()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found in this school")
    marks = db.query(Mark).filter(Mark.school_id == sid, Mark.assessment_id == assessment_id, Mark.status == "approved").all()
    if not marks:
        raise HTTPException(status_code=409, detail="No approved marks are available to publish")
    from datetime import datetime, timezone
    for m in marks:
        m.status = "published"
        m.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    from app.models.notification import Notification
    from app.models.student import Contact
    students = {m.student_id for m in marks}
    for st_id in students:
        contacts = db.query(Contact).filter(Contact.student_id == st_id, Contact.school_id == sid, Contact.is_primary == True).all()
        for c in contacts:
            if c.email:
                dedupe = f"results-published:{assessment_id}:{st_id}:email"
                exists = db.query(Notification).filter(Notification.dedupe_key == dedupe).first()
                if not exists:
                    db.add(Notification(school_id=sid, dedupe_key=dedupe, channel="email", recipient=c.email, payload={"assessment_id": assessment_id, "student_id": st_id}, status="queued"))
            if c.phone:
                dedupe = f"results-published:{assessment_id}:{st_id}:sms"
                exists = db.query(Notification).filter(Notification.dedupe_key == dedupe).first()
                if not exists:
                    db.add(Notification(school_id=sid, dedupe_key=dedupe, channel="sms", recipient=c.phone, payload={"assessment_id": assessment_id, "student_id": st_id}, status="queued"))
    db.commit()
    write_audit(db, principal, "marks.publish", "assessment", assessment_id, {"count": len(marks)}, school_id=sid)
    return {"published": len(marks)}


@router.get("/report-card/{student_id}")
def report_card(student_id: int, term_id: Optional[int] = None, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'teacher')), db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    if not principal.is_admin and principal.school_id != student.school_id:
        raise HTTPException(status_code=403, detail="Access denied")
    q = db.query(Mark, Assessment, Subject).join(Assessment, Assessment.id == Mark.assessment_id).join(Subject, Subject.id == Assessment.subject_id).filter(Mark.school_id == student.school_id, Assessment.school_id == student.school_id, Subject.school_id == student.school_id, Mark.student_id == student_id, Mark.status == "published")
    if term_id is not None:
        if db.query(Term).filter(Term.id == term_id, Term.school_id == student.school_id).first() is None:
            raise HTTPException(status_code=404, detail="Term not found in this school")
        q = q.filter(Assessment.term_id == term_id)
    rows = q.all()
    # aggregate per subject
    subjects = {}
    for mark, assessment, subject in rows:
        subjects.setdefault(subject.name, []).append((assessment.name, float(mark.score), float(assessment.max_score), float(assessment.weight)))
    result = []
    for name, items in subjects.items():
        total_weight = sum(w for _, _, _, w in items)
        weighted = sum((s / mx) * w for _, s, mx, w in items) if total_weight else 0
        avg = (weighted / total_weight * 100) if total_weight else 0
        result.append({"subject": name, "average": round(avg, 2), "assessments": [{"name": a, "score": s, "max": mx} for a, s, mx, _ in items]})
    return {"student_id": student.id, "student_number": student.student_number, "name": f"{student.first_name} {student.last_name}", "subjects": result}

