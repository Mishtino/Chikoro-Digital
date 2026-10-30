from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_principal, Principal
from app.models.results import Subject, Assessment, Mark
from app.models.student import Student
from app.models.fee import Term
from app.services.audit import write_audit

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


def _sid(principal: Principal, requested: Optional[int]) -> int:
    if principal.is_admin:
        if requested is None:
            raise HTTPException(status_code=400, detail="school_id required")
        return requested
    if principal.school_id is None:
        raise HTTPException(status_code=403, detail="School context required")
    return principal.school_id


@router.post("/subjects", status_code=status.HTTP_201_CREATED)
def create_subject(payload: SubjectCreate, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    sid = _sid(principal, payload.school_id)
    subject = Subject(school_id=sid, name=payload.name, code=payload.code)
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return {"id": subject.id, "name": subject.name, "code": subject.code}


@router.get("/subjects")
def list_subjects(school_id: Optional[int] = Query(None), principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id) if (principal.is_admin or school_id is not None) else principal.school_id
    if sid is None:
        raise HTTPException(status_code=403, detail="School context required")
    return db.query(Subject).filter(Subject.school_id == sid).order_by(Subject.id).all()


@router.post("/assessments", status_code=status.HTTP_201_CREATED)
def create_assessment(payload: AssessmentCreate, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    sid = _sid(principal, payload.school_id)
    a = Assessment(school_id=sid, subject_id=payload.subject_id, term_id=payload.term_id, name=payload.name, weight=payload.weight, max_score=payload.max_score)
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"id": a.id}


@router.get("/assessments")
def list_assessments(subject_id: Optional[int] = Query(None), term_id: Optional[int] = Query(None), school_id: Optional[int] = Query(None), principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id) if (principal.is_admin or school_id is not None) else principal.school_id
    if sid is None:
        raise HTTPException(status_code=403, detail="School context required")
    q = db.query(Assessment).filter(Assessment.school_id == sid)
    if subject_id is not None:
        q = q.filter(Assessment.subject_id == subject_id)
    if term_id is not None:
        q = q.filter(Assessment.term_id == term_id)
    return q.order_by(Assessment.id).all()


@router.post("/marks")
def enter_marks(payload: BulkMarksRequest, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    sid = _sid(principal, payload.school_id)
    created = 0
    for e in payload.entries:
        existing = db.query(Mark).filter(Mark.school_id == sid, Mark.student_id == e.student_id, Mark.assessment_id == e.assessment_id).first()
        if existing:
            existing.score = e.score
            existing.entered_by_user_id = principal.user_id
        else:
            db.add(Mark(school_id=sid, student_id=e.student_id, assessment_id=e.assessment_id, score=e.score, entered_by_user_id=principal.user_id))
        created += 1
    db.commit()
    write_audit(db, principal, "marks.enter", "assessment", None, {"count": created}, school_id=sid)
    return {"saved": created}


@router.post("/marks/approve")
def approve_marks(assessment_id: int, school_id: Optional[int] = None, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id)
    updated = db.query(Mark).filter(Mark.school_id == sid, Mark.assessment_id == assessment_id).update({"status": "approved"})
    db.commit()
    return {"approved": updated}
@router.post("/marks/publish")
def publish_marks(assessment_id: int, school_id: Optional[int] = None, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id)
    marks = db.query(Mark).filter(Mark.school_id == sid, Mark.assessment_id == assessment_id).all()
    from datetime import datetime, timezone
    for m in marks:
        m.status = "published"
        m.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    from app.models.notification import Notification
    from app.models.student import Contact
    students = {m.student_id for m in marks}
    for st_id in students:
        contacts = db.query(Contact).filter(Contact.student_id == st_id, Contact.is_primary == True).all()
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
def report_card(student_id: int, term_id: Optional[int] = None, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    if not principal.is_admin and principal.school_id != student.school_id:
        raise HTTPException(status_code=403, detail="Access denied")
    q = db.query(Mark, Assessment, Subject).join(Assessment, Assessment.id == Mark.assessment_id).join(Subject, Subject.id == Assessment.subject_id).filter(Mark.student_id == student_id, Mark.status == "published")
    if term_id is not None:
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

