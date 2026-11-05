from typing import List, Optional
from xml.sax.saxutils import escape
import math

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.database import get_db
from app.deps_supabase import SupabasePrincipal, require_supabase_roles
from app.models.results import Subject, Assessment, Mark
from app.models.student import Student
from app.models.fee import Term
from app.services.audit import write_audit
from app.services.class_access import require_teacher_class, assigned_class_names

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
    if principal.is_platform_admin:
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
    sid = _sid(principal, school_id) if (principal.is_platform_admin or school_id is not None) else principal.school_id
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
    sid = _sid(principal, school_id) if (principal.is_platform_admin or school_id is not None) else principal.school_id
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
    db.flush()
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
    sid = _sid(principal, school_id) if (principal.is_platform_admin or school_id is not None) else principal.school_id
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
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id, Assessment.school_id == sid
    ).with_for_update().first()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found in this school")
    updated = db.query(Mark).filter(
        Mark.school_id == sid,
        Mark.assessment_id == assessment_id,
        Mark.status == "draft",
    ).update({"status": "approved"}, synchronize_session=False)
    # write_audit commits the state transition and audit record together.
    write_audit(db, principal, "marks.approve", "assessment", assessment_id, {"count": updated}, school_id=sid)
    return {"approved": updated}


@router.post("/marks/publish")
def publish_marks(assessment_id: int, school_id: Optional[int] = None, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster')), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id)
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id, Assessment.school_id == sid
    ).with_for_update().first()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found in this school")

    # Lock the assessment first so concurrent publish requests serialize.
    marks = (
        db.query(Mark)
        .filter(
            Mark.school_id == sid,
            Mark.assessment_id == assessment_id,
            Mark.status == "approved",
        )
        .order_by(Mark.id)
        .with_for_update()
        .all()
    )
    if not marks:
        raise HTTPException(status_code=409, detail="No approved marks are available to publish")

    from datetime import datetime, timezone
    for mark in marks:
        mark.status = "published"
        mark.published_at = datetime.now(timezone.utc).replace(tzinfo=None)

    from app.models.notification import Notification
    from app.models.student import Contact
    student_ids = {mark.student_id for mark in marks}
    contacts = (
        db.query(Contact)
        .filter(
            Contact.student_id.in_(student_ids),
            Contact.school_id == sid,
            Contact.is_primary.is_(True),
        )
        .order_by(Contact.id)
        .all()
    )
    queued_channels = set()
    for contact in contacts:
        # The dedupe key is per learner/channel; tolerate multiple primary
        # contact rows without creating duplicate queue entries.
        if contact.email and (contact.student_id, "email") not in queued_channels:
            dedupe = f"results-published:{assessment_id}:{contact.student_id}:email"
            db.add(Notification(
                school_id=sid, dedupe_key=dedupe, channel="email",
                recipient=contact.email,
                payload={"assessment_id": assessment_id, "student_id": contact.student_id},
                status="queued",
            ))
            queued_channels.add((contact.student_id, "email"))
        if contact.phone and (contact.student_id, "sms") not in queued_channels:
            dedupe = f"results-published:{assessment_id}:{contact.student_id}:sms"
            db.add(Notification(
                school_id=sid, dedupe_key=dedupe, channel="sms",
                recipient=contact.phone,
                payload={"assessment_id": assessment_id, "student_id": contact.student_id},
                status="queued",
            ))
            queued_channels.add((contact.student_id, "sms"))

    # A single commit persists publication, queued notifications and audit.
    write_audit(
        db, principal, "marks.publish", "assessment", assessment_id,
        {"count": len(marks)}, school_id=sid,
    )
    return {"published": len(marks)}


@router.get("/analytics/class-performance")
def class_performance_analytics(
    term_id: Optional[int] = Query(None),
    subject_id: Optional[int] = Query(None),
    class_name: Optional[str] = Query(None),
    school_id: Optional[int] = Query(None),
    principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'teacher')),
    db: Session = Depends(get_db),
):
    """Return aggregated published-mark performance, restricted to assigned teacher classes."""
    sid = _sid(principal, school_id) if (principal.is_platform_admin or school_id is not None) else principal.school_id
    if sid is None or principal.is_admin:
        raise HTTPException(status_code=403, detail="School academic access required")
    if term_id is not None and db.query(Term).filter(
        Term.id == term_id, Term.school_id == sid
    ).first() is None:
        raise HTTPException(status_code=404, detail="Term not found in this school")
    if subject_id is not None and db.query(Subject).filter(
        Subject.id == subject_id, Subject.school_id == sid
    ).first() is None:
        raise HTTPException(status_code=404, detail="Subject not found in this school")

    query = (
        db.query(
            Student.form.label("class_name"),
            Subject.id.label("subject_id"),
            Subject.name.label("subject_name"),
            func.count(Mark.id).label("mark_count"),
            func.count(func.distinct(Student.id)).label("learner_count"),
            func.avg((Mark.score / Assessment.max_score) * 100).label("average_percent"),
            func.sum(case((Mark.score >= Assessment.max_score * 0.5, 1), else_=0)).label("pass_count"),
        )
        .join(Student, (Student.id == Mark.student_id) & (Student.school_id == Mark.school_id))
        .join(Assessment, (Assessment.id == Mark.assessment_id) & (Assessment.school_id == Mark.school_id))
        .join(Subject, (Subject.id == Assessment.subject_id) & (Subject.school_id == Assessment.school_id))
        .filter(
            Mark.school_id == sid,
            Student.school_id == sid,
            Student.status == "active",
            Assessment.school_id == sid,
            Subject.school_id == sid,
            Mark.status == "published",
        )
    )
    if term_id is not None:
        query = query.filter(Assessment.term_id == term_id)
    if subject_id is not None:
        query = query.filter(Subject.id == subject_id)
    if class_name is not None:
        query = query.filter(Student.form == class_name)
    if principal.role == "teacher" and not principal.is_admin:
        allowed = assigned_class_names(db, principal, sid)
        if not allowed:
            return {"school_id": sid, "term_id": term_id, "results": []}
        if class_name is not None and class_name not in allowed:
            raise HTTPException(status_code=403, detail="You are not assigned to this class")
        query = query.filter(Student.form.in_(sorted(allowed)))

    rows = query.group_by(Student.form, Subject.id, Subject.name).order_by(
        Student.form, Subject.name
    ).limit(500).all()
    results = []
    for row in rows:
        marks = int(row.mark_count or 0)
        passes = int(row.pass_count or 0)
        results.append({
            "class_name": row.class_name,
            "subject_id": row.subject_id,
            "subject_name": row.subject_name,
            "learner_count": int(row.learner_count or 0),
            "mark_count": marks,
            "average_percent": round(float(row.average_percent or 0), 2),
            "pass_rate_percent": round(passes / marks * 100, 2) if marks else None,
        })
    return {"school_id": sid, "term_id": term_id, "results": results}


@router.get("/analytics/subject-trends")
def subject_performance_trends(
    subject_id: Optional[int] = Query(None),
    class_name: Optional[str] = Query(None),
    school_id: Optional[int] = Query(None),
    principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'teacher')),
    db: Session = Depends(get_db),
):
    """Return term-by-term published performance for a subject, optionally limited to a class."""
    sid = _sid(principal, school_id) if (principal.is_platform_admin or school_id is not None) else principal.school_id
    if sid is None or principal.is_admin:
        raise HTTPException(status_code=403, detail="School academic access required")
    if subject_id is not None and db.query(Subject).filter(
        Subject.id == subject_id, Subject.school_id == sid
    ).first() is None:
        raise HTTPException(status_code=404, detail="Subject not found in this school")

    query = db.query(
        Term.id.label("term_id"),
        Term.name.label("term_name"),
        Term.academic_year.label("academic_year"),
        Subject.id.label("subject_id"),
        Subject.name.label("subject_name"),
        Student.form.label("class_name"),
        func.count(Mark.id).label("mark_count"),
        func.count(func.distinct(Student.id)).label("learner_count"),
        func.avg((Mark.score / Assessment.max_score) * 100).label("average_percent"),
        func.sum(case((Mark.score >= Assessment.max_score * 0.5, 1), else_=0)).label("pass_count"),
    ).join(
        Assessment, (Assessment.term_id == Term.id) & (Assessment.school_id == Term.school_id)
    ).join(
        Mark, (Mark.assessment_id == Assessment.id) & (Mark.school_id == Assessment.school_id)
    ).join(
        Student, (Student.id == Mark.student_id) & (Student.school_id == Mark.school_id)
    ).join(
        Subject, (Subject.id == Assessment.subject_id) & (Subject.school_id == Assessment.school_id)
    ).filter(
        Term.school_id == sid,
        Assessment.school_id == sid,
        Mark.school_id == sid,
        Student.school_id == sid,
        Student.status == "active",
        Subject.school_id == sid,
        Mark.status == "published",
    )
    if subject_id is not None:
        query = query.filter(Subject.id == subject_id)
    if class_name is not None:
        query = query.filter(Student.form == class_name)
    if principal.role == "teacher" and not principal.is_admin:
        allowed = assigned_class_names(db, principal, sid)
        if not allowed:
            return {"school_id": sid, "trends": []}
        if class_name is not None and class_name not in allowed:
            raise HTTPException(status_code=403, detail="You are not assigned to this class")
        query = query.filter(Student.form.in_(sorted(allowed)))

    rows = query.group_by(
        Term.id, Term.name, Term.academic_year,
        Subject.id, Subject.name, Student.form,
    ).order_by(
        Term.academic_year, Term.id, Subject.name, Student.form,
    ).limit(1000).all()
    trends = []
    for row in rows:
        count = int(row.mark_count or 0)
        passes = int(row.pass_count or 0)
        trends.append({
            "term_id": row.term_id,
            "term_name": row.term_name,
            "academic_year": row.academic_year,
            "subject_id": row.subject_id,
            "subject_name": row.subject_name,
            "class_name": row.class_name,
            "learner_count": int(row.learner_count or 0),
            "mark_count": count,
            "average_percent": round(float(row.average_percent or 0), 2),
            "pass_rate_percent": round(passes / count * 100, 2) if count else None,
        })
    return {"school_id": sid, "trends": trends}



@router.get("/report-card/{student_id}")
def report_card(student_id: int, term_id: Optional[int] = None, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'teacher')), db: Session = Depends(get_db)):
    if principal.is_admin or principal.role not in {"owner", "headmaster", "teacher"} or principal.school_id is None:
        raise HTTPException(status_code=403, detail="School academic access required")
    student = db.query(Student).filter(
        Student.id == student_id, Student.school_id == principal.school_id
    ).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    if principal.role == "teacher":
        require_teacher_class(db, principal, student.school_id, student.form or "")
    q = db.query(Mark, Assessment, Subject).join(Assessment, Assessment.id == Mark.assessment_id).join(Subject, Subject.id == Assessment.subject_id).filter(Mark.school_id == student.school_id, Assessment.school_id == student.school_id, Subject.school_id == student.school_id, Mark.student_id == student_id, Mark.status == "published")
    if term_id is not None:
        if db.query(Term).filter(Term.id == term_id, Term.school_id == student.school_id).first() is None:
            raise HTTPException(status_code=404, detail="Term not found in this school")
        q = q.filter(Assessment.term_id == term_id)
    rows = q.all()
    # aggregate per subject
    subjects = {}
    for mark, assessment, subject in rows:
        subjects.setdefault(subject.id, {"name": subject.name, "items": []})["items"].append((assessment.name, float(mark.score), float(assessment.max_score), float(assessment.weight)))
    result = []
    for subject_id, group in subjects.items():
        items = group["items"]
        total_weight = sum(w for _, _, _, w in items)
        weighted = sum((s / mx) * w for _, s, mx, w in items) if total_weight else 0
        avg = (weighted / total_weight * 100) if total_weight else 0
        result.append({"subject_id": subject_id, "subject": group["name"], "average": round(avg, 2), "assessments": [{"name": a, "score": s, "max": mx} for a, s, mx, _ in items]})
    return {"student_id": student.id, "student_number": student.student_number, "name": f"{student.first_name} {student.last_name}", "subjects": result}

@router.get("/report-card/{student_id}/pdf")
def download_report_card_pdf(
    student_id: int,
    term_id: Optional[int] = Query(None),
    principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'teacher')),
    db: Session = Depends(get_db),
):
    """Generate a downloadable PDF using the same school and class checks as the JSON report card."""
    from io import BytesIO
    from fastapi.responses import StreamingResponse
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    data = report_card(student_id, term_id, principal, db)
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Report card - {data['student_number']}",
        author="Chikoro Digital",
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("CHIKORO DIGITAL", styles["Title"]),
        Paragraph("STUDENT REPORT CARD", styles["Heading2"]),
        Spacer(1, 5 * mm),
        Paragraph(f"<b>Learner:</b> {escape(str(data['name']))}", styles["BodyText"]),
        Paragraph(f"<b>Student number:</b> {escape(str(data['student_number']))}", styles["BodyText"]),
    ]
    if term_id is not None:
        term = db.query(Term).filter(Term.id == term_id, Term.school_id == principal.school_id).first()
        story.append(Paragraph(f"<b>Term:</b> {escape(str(term.name))}", styles["BodyText"]))
    story.append(Spacer(1, 7 * mm))
    table_data = [["Subject", "Average (%)", "Assessment", "Score"]]
    for subject in data["subjects"]:
        if not subject["assessments"]:
            table_data.append([subject["subject"], f"{subject['average']:.2f}", "—", "—"])
        else:
            for index, assessment in enumerate(subject["assessments"]):
                table_data.append([
                    subject["subject"] if index == 0 else "",
                    f"{subject['average']:.2f}" if index == 0 else "",
                    assessment["name"],
                    f"{assessment['score']:g} / {assessment['max']:g}",
                ])
    if len(table_data) == 1:
        table_data.append(["No published results", "", "", ""])
    table = Table(table_data, colWidths=[42 * mm, 28 * mm, 70 * mm, 30 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B7C3D0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6FA")]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([table, Spacer(1, 8 * mm), Paragraph(
        "This report contains published assessment results only.", styles["Italic"]
    )])
    document.build(story)
    buffer.seek(0)
    filename = f"report-card-{data['student_number']}" + (f"-term-{term_id}" if term_id else "") + ".pdf"
    return StreamingResponse(
        buffer, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

