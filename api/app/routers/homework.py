from datetime import datetime, timezone
import math
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps_supabase import SupabasePrincipal, get_supabase_principal, require_supabase_roles
from app.models.homework import HomeworkAssignment, HomeworkSubmission, HomeworkAttachment
from app.models.results import Subject
from app.models.student import Student
from app.models.fee import Term
from app.services.audit import write_audit
from app.services.class_access import require_teacher_class
from app.routers.portal import _parent_student, _student_portal_student
from app.services.homework_storage import (
    StorageOperationError, create_upload_url, create_download_url, inspect_object,
)

router = APIRouter(prefix="/homework", tags=["homework"])


class AssignmentCreate(BaseModel):
    class_name: str = Field(min_length=1, max_length=40)
    subject_id: int
    term_id: Optional[int] = None
    title: str = Field(min_length=1, max_length=160)
    instructions: str = Field(min_length=1, max_length=10000)
    due_at: Optional[datetime] = None
    publish: bool = False

    @field_validator("class_name", "title", "instructions")
    @classmethod
    def strip_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value


class SubmissionCreate(BaseModel):
    answer_text: str = Field(min_length=1, max_length=20000)

    @field_validator("answer_text")
    @classmethod
    def strip_answer(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Answer cannot be blank")
        return value


class SubmissionMark(BaseModel):
    feedback: Optional[str] = Field(default=None, max_length=5000)
    score: Optional[float] = Field(default=None, ge=0)

    @field_validator("score")
    @classmethod
    def finite_score(cls, value):
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError("Score must be a finite non-negative number")
        return value


def _school_id(principal: SupabasePrincipal) -> int:
    if principal.school_id is None or principal.is_admin:
        raise HTTPException(status_code=403, detail="School-scoped access required")
    return principal.school_id


def _assignment_out(assignment, subject):
    return {
        "id": assignment.id, "class_name": assignment.class_name,
        "subject_id": assignment.subject_id, "subject_name": subject.name,
        "term_id": assignment.term_id, "title": assignment.title,
        "instructions": assignment.instructions,
        "due_at": assignment.due_at.isoformat() if assignment.due_at else None,
        "status": assignment.status,
    }


@router.post("/assignments", status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreate,
    principal: SupabasePrincipal = Depends(require_supabase_roles("owner", "headmaster", "teacher")),
    db: Session = Depends(get_db),
):
    sid = _school_id(principal)
    if principal.role == "teacher":
        require_teacher_class(db, principal, sid, payload.class_name)
    subject = db.query(Subject).filter(Subject.id == payload.subject_id, Subject.school_id == sid).first()
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found in this school")
    if payload.term_id is not None and db.query(Term).filter(Term.id == payload.term_id, Term.school_id == sid).first() is None:
        raise HTTPException(status_code=404, detail="Term not found in this school")
    due_at = payload.due_at
    if due_at is not None and due_at.tzinfo is not None:
        due_at = due_at.astimezone(timezone.utc).replace(tzinfo=None)
    assignment = HomeworkAssignment(
        school_id=sid, class_name=payload.class_name, subject_id=payload.subject_id,
        term_id=payload.term_id, title=payload.title, instructions=payload.instructions,
        due_at=due_at, status="published" if payload.publish else "draft",
        created_by_user_id=principal.user_id,
        published_at=datetime.now(timezone.utc).replace(tzinfo=None) if payload.publish else None,
    )
    db.add(assignment)
    db.flush()
    db.refresh(assignment)$3(db, principal, "homework.assignment.create", "homework_assignment", assignment.id,
                {"class_name": assignment.class_name, "status": assignment.status}, school_id=sid)
    return {"id": assignment.id, "status": assignment.status}


@router.get("/assignments")
def list_assignments(
    class_name: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    principal: SupabasePrincipal = Depends(require_supabase_roles("owner", "headmaster", "teacher")),
    db: Session = Depends(get_db),
):
    sid = _school_id(principal)
    query = db.query(HomeworkAssignment, Subject).join(
        Subject, (Subject.id == HomeworkAssignment.subject_id) & (Subject.school_id == HomeworkAssignment.school_id)
    ).filter(HomeworkAssignment.school_id == sid)
    if class_name:
        query = query.filter(HomeworkAssignment.class_name == class_name)
    if status_filter:
        if status_filter not in {"draft", "published", "closed"}:
            raise HTTPException(status_code=422, detail="Invalid assignment status")
        query = query.filter(HomeworkAssignment.status == status_filter)
    if principal.role == "teacher":
        query = query.filter(HomeworkAssignment.created_by_user_id == principal.user_id)
    rows = query.order_by(HomeworkAssignment.created_at.desc()).limit(500).all()
    if principal.role == "teacher":
        rows = [
            (assignment, subject) for assignment, subject in rows
            if require_teacher_class(db, principal, sid, assignment.class_name)
        ]
    return {"assignments": [_assignment_out(a, s) for a, s in rows]}


@router.get("/assignments/{assignment_id}/submissions")
def list_submissions(
    assignment_id: int,
    principal: SupabasePrincipal = Depends(require_supabase_roles("owner", "headmaster", "teacher")),
    db: Session = Depends(get_db),
):
    sid = _school_id(principal)
    assignment = db.query(HomeworkAssignment).filter(
        HomeworkAssignment.id == assignment_id, HomeworkAssignment.school_id == sid
    ).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if principal.role == "teacher":
        if assignment.created_by_user_id != principal.user_id:
            raise HTTPException(status_code=404, detail="Assignment not found")
        require_teacher_class(db, principal, sid, assignment.class_name)
    rows = db.query(HomeworkSubmission, Student).join(
        Student, (Student.id == HomeworkSubmission.student_id) & (Student.school_id == HomeworkSubmission.school_id)
    ).filter(
        HomeworkSubmission.school_id == sid,
        HomeworkSubmission.assignment_id == assignment.id,
    ).order_by(HomeworkSubmission.submitted_at.desc()).limit(1000).all()
    return {"submissions": [
        {"id": sub.id, "student_id": student.id, "student_number": student.student_number,
         "student_name": f"{student.first_name} {student.last_name}", "answer_text": sub.answer_text,
         "status": sub.status, "submitted_at": sub.submitted_at.isoformat(),
         "feedback": sub.feedback, "score": float(sub.score) if sub.score is not None else None,
         "attachments": _ready_attachment_out(db, sid, sub.id)}
        for sub, student in rows
    ]}


@router.post("/submissions/{submission_id}/mark")
def mark_submission(
    submission_id: int,
    payload: SubmissionMark,
    principal: SupabasePrincipal = Depends(require_supabase_roles("owner", "headmaster", "teacher")),
    db: Session = Depends(get_db),
):
    sid = _school_id(principal)
    submission = db.query(HomeworkSubmission).filter(
        HomeworkSubmission.id == submission_id, HomeworkSubmission.school_id == sid
    ).with_for_update().first()
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    assignment = db.query(HomeworkAssignment).filter(
        HomeworkAssignment.id == submission.assignment_id, HomeworkAssignment.school_id == sid
    ).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    if principal.role == "teacher":
        if assignment.created_by_user_id != principal.user_id:
            raise HTTPException(status_code=404, detail="Submission not found")
        require_teacher_class(db, principal, sid, assignment.class_name)
    submission.feedback = payload.feedback.strip() if payload.feedback else None
    submission.score = payload.score
    submission.status = "marked"
    submission.marked_by_user_id = principal.user_id
    submission.marked_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.flush()
    write_audit(db, principal, "homework.submission.mark", "homework_submission", submission.id,
                {"has_score": payload.score is not None}, school_id=sid)
    return {"id": submission.id, "status": submission.status}


@router.get("/student/assignments")
def student_assignments(
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    student = _student_portal_student(principal, db)
    rows = db.query(HomeworkAssignment, Subject, HomeworkSubmission).join(
        Subject, (Subject.id == HomeworkAssignment.subject_id) & (Subject.school_id == HomeworkAssignment.school_id)
    ).outerjoin(
        HomeworkSubmission,
        (HomeworkSubmission.assignment_id == HomeworkAssignment.id)
        & (HomeworkSubmission.student_id == student.id)
        & (HomeworkSubmission.school_id == student.school_id),
    ).filter(
        HomeworkAssignment.school_id == student.school_id,
        HomeworkAssignment.class_name == (student.form or ""),
        HomeworkAssignment.status == "published",
    ).order_by(HomeworkAssignment.due_at.asc(), HomeworkAssignment.id.desc()).limit(500).all()
    return {"attachments_enabled": settings.homework_attachments_enabled, "assignments": [
        {**_assignment_out(a, subject),
         "submission_status": submission.status if submission else "not_submitted",
         "submission_id": submission.id if submission else None,
         "attachments": _ready_attachment_out(db, student.school_id, submission.id) if submission else [],
         "submitted_at": submission.submitted_at.isoformat() if submission else None,
         "feedback": submission.feedback if submission else None,
         "score": float(submission.score) if submission and submission.score is not None else None}
        for a, subject, submission in rows
    ]}


@router.post("/student/assignments/{assignment_id}/submit", status_code=status.HTTP_201_CREATED)
def submit_homework(
    assignment_id: int,
    payload: SubmissionCreate,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    student = _student_portal_student(principal, db)
    assignment = db.query(HomeworkAssignment).filter(
        HomeworkAssignment.id == assignment_id,
        HomeworkAssignment.school_id == student.school_id,
        HomeworkAssignment.class_name == (student.form or ""),
        HomeworkAssignment.status == "published",
    ).with_for_update().first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Published assignment not found")
    if assignment.due_at is not None:
        due = assignment.due_at
        if due.tzinfo is not None:
            due = due.replace(tzinfo=None)
        if datetime.now(timezone.utc).replace(tzinfo=None) > due:
            raise HTTPException(status_code=409, detail="The submission deadline has passed")
    existing = db.query(HomeworkSubmission).filter(
        HomeworkSubmission.school_id == student.school_id,
        HomeworkSubmission.assignment_id == assignment.id,
        HomeworkSubmission.student_id == student.id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="A submission already exists for this assignment")
    submission = HomeworkSubmission(
        school_id=student.school_id, assignment_id=assignment.id, student_id=student.id,
        answer_text=payload.answer_text,
    )
    db.add(submission)
    db.flush()
    db.refresh(submission)$3(db, principal, "homework.submission.create", "homework_submission", submission.id,
                {"assignment_id": assignment.id}, school_id=student.school_id)
    return {"id": submission.id, "status": submission.status, "submitted_at": submission.submitted_at.isoformat()}


@router.get("/parent/children/{student_id}/assignments")
def parent_child_assignments(
    student_id: int,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    student = _parent_student(principal, student_id, db)
    rows = db.query(HomeworkAssignment, Subject, HomeworkSubmission).join(
        Subject, (Subject.id == HomeworkAssignment.subject_id) & (Subject.school_id == HomeworkAssignment.school_id)
    ).outerjoin(
        HomeworkSubmission,
        (HomeworkSubmission.assignment_id == HomeworkAssignment.id)
        & (HomeworkSubmission.student_id == student.id)
        & (HomeworkSubmission.school_id == student.school_id),
    ).filter(
        HomeworkAssignment.school_id == student.school_id,
        HomeworkAssignment.class_name == (student.form or ""),
        HomeworkAssignment.status == "published",
    ).order_by(HomeworkAssignment.due_at.asc(), HomeworkAssignment.id.desc()).limit(500).all()
    return {"attachments_enabled": settings.homework_attachments_enabled, "assignments": [
        {**_assignment_out(a, subject),
         "submission_status": submission.status if submission else "not_submitted",
         "submission_id": submission.id if submission else None,
         "attachments": _ready_attachment_out(db, student.school_id, submission.id) if submission else [],
         "submitted_at": submission.submitted_at.isoformat() if submission else None,
         "feedback": submission.feedback if submission else None,
         "score": float(submission.score) if submission and submission.score is not None else None}
        for a, subject, submission in rows
    ]}



MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS_PER_SUBMISSION = 5

def _require_attachments_enabled():
    if not settings.homework_attachments_enabled:
        raise HTTPException(status_code=404, detail="Attachment feature is not available")


ALLOWED_ATTACHMENT_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "image/jpeg": "jpg",
    "image/png": "png",
    "text/plain": "txt",
}


class AttachmentUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(gt=0, le=MAX_ATTACHMENT_BYTES)

    @field_validator("filename", "content_type")
    @classmethod
    def clean_attachment_text(cls, value):
        value = value.strip()
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("Invalid attachment metadata")
        return value


def _ready_attachment_out(db, school_id, submission_id):
    if not settings.homework_attachments_enabled:
        return []
    rows = db.query(HomeworkAttachment).filter(
        HomeworkAttachment.school_id == school_id,
        HomeworkAttachment.submission_id == submission_id,
        HomeworkAttachment.status == "ready",
    ).order_by(HomeworkAttachment.created_at.asc()).all()
    return [_attachment_out(row) for row in rows]


def _attachment_out(attachment):
    return {
        "id": attachment.id,
        "filename": attachment.original_filename,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "status": attachment.status,
        "created_at": attachment.created_at.isoformat(),
    }


def _submission_and_assignment(db, school_id, submission_id, lock=False):
    query = db.query(HomeworkSubmission).filter(
        HomeworkSubmission.id == submission_id,
        HomeworkSubmission.school_id == school_id,
    )
    if lock:
        query = query.with_for_update()
    submission = query.first()
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    assignment = db.query(HomeworkAssignment).filter(
        HomeworkAssignment.id == submission.assignment_id,
        HomeworkAssignment.school_id == school_id,
    ).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    return submission, assignment


@router.post("/student/submissions/{submission_id}/attachments/upload-url", status_code=status.HTTP_201_CREATED)
def create_homework_attachment_upload(
    submission_id: int,
    payload: AttachmentUploadRequest,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    _require_attachments_enabled()
    if principal.role != "student":
        raise HTTPException(status_code=403, detail="Student access required")
    student = _student_portal_student(principal, db)
    submission, assignment = _submission_and_assignment(db, student.school_id, submission_id, lock=True)
    if submission.student_id != student.id or assignment.status != "published" or submission.status != "submitted":
        raise HTTPException(status_code=404, detail="Submission not found")
    if assignment.due_at is not None:
        due = assignment.due_at.replace(tzinfo=None) if assignment.due_at.tzinfo is not None else assignment.due_at
        if datetime.now(timezone.utc).replace(tzinfo=None) > due:
            raise HTTPException(status_code=409, detail="The attachment deadline has passed")
    content_type = payload.content_type.lower()
    extension = ALLOWED_ATTACHMENT_TYPES.get(content_type)
    if extension is None:
        raise HTTPException(status_code=415, detail="File type is not allowed")
    filename = payload.filename.replace("\\", "/").split("/")[-1].strip()
    if not filename or filename in {".", ".."}:
        raise HTTPException(status_code=422, detail="Invalid filename")
    count = db.query(HomeworkAttachment).filter(
        HomeworkAttachment.school_id == student.school_id,
        HomeworkAttachment.submission_id == submission.id,
    ).count()
    if count >= MAX_ATTACHMENTS_PER_SUBMISSION:
        raise HTTPException(status_code=409, detail="Maximum of five attachments reached")
    object_path = (
        f"schools/{student.school_id}/assignments/{assignment.id}/"
        f"submissions/{submission.id}/{uuid4().hex}.{extension}"
    )
    try:
        upload_url = create_upload_url(object_path)
    except StorageOperationError:
        raise HTTPException(status_code=503, detail="Private file storage is unavailable") from None
    attachment = HomeworkAttachment(
        school_id=student.school_id,
        submission_id=submission.id,
        uploaded_by_user_id=principal.user_id,
        object_path=object_path,
        original_filename=filename[:255],
        content_type=content_type,
        size_bytes=payload.size_bytes,
        status="pending",
    )
    db.add(attachment)
    db.flush()
    db.refresh(attachment)$3(
        db, principal, "homework.attachment.upload_url", "homework_attachment",
        attachment.id, {"submission_id": submission.id, "size_bytes": payload.size_bytes},
        school_id=student.school_id,
    )
    return {
        "attachment": _attachment_out(attachment),
        "upload_url": upload_url,
        "method": "PUT",
        "expires_in_seconds": 7200,
    }


@router.post("/student/attachments/{attachment_id}/complete")
def complete_homework_attachment_upload(
    attachment_id: int,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    _require_attachments_enabled()
    if principal.role != "student":
        raise HTTPException(status_code=403, detail="Student access required")
    student = _student_portal_student(principal, db)
    attachment = db.query(HomeworkAttachment).filter(
        HomeworkAttachment.id == attachment_id,
        HomeworkAttachment.school_id == student.school_id,
        HomeworkAttachment.uploaded_by_user_id == principal.user_id,
    ).first()
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    if attachment.status == "ready":
        return {"id": attachment.id, "status": "ready"}
    try:
        stored = inspect_object(attachment.object_path)
    except StorageOperationError:
        raise HTTPException(status_code=409, detail="Uploaded file could not be verified") from None
    if (
        stored["size_bytes"] != attachment.size_bytes
        or stored["size_bytes"] > MAX_ATTACHMENT_BYTES
        or stored["content_type"] != attachment.content_type
    ):
        raise HTTPException(status_code=422, detail="Uploaded file metadata does not match the request")
    attachment.status = "ready"
    db.flush()
    write_audit(
        db, principal, "homework.attachment.complete", "homework_attachment",
        attachment.id, {"size_bytes": attachment.size_bytes}, school_id=student.school_id,
    )
    return {"id": attachment.id, "status": "ready"}


@router.get("/submissions/{submission_id}/attachments")
def list_homework_attachments(
    submission_id: int,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    _require_attachments_enabled()
    sid = _school_id(principal)
    submission, assignment = _submission_and_assignment(db, sid, submission_id)
    if principal.role == "student":
        student = _student_portal_student(principal, db)
        if submission.student_id != student.id:
            raise HTTPException(status_code=404, detail="Submission not found")
    elif principal.role == "parent":
        _parent_student(principal, submission.student_id, db)
    elif principal.role == "teacher":
        if assignment.created_by_user_id != principal.user_id:
            raise HTTPException(status_code=404, detail="Submission not found")
        require_teacher_class(db, principal, sid, assignment.class_name)
    elif principal.role not in {"owner", "headmaster"}:
        raise HTTPException(status_code=403, detail="Role cannot access attachments")
    rows = db.query(HomeworkAttachment).filter(
        HomeworkAttachment.school_id == sid,
        HomeworkAttachment.submission_id == submission.id,
        HomeworkAttachment.status == "ready",
    ).order_by(HomeworkAttachment.created_at.asc()).all()
    return {"attachments": [_attachment_out(row) for row in rows]}


@router.post("/attachments/{attachment_id}/download-url")
def create_homework_attachment_download(
    attachment_id: int,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    _require_attachments_enabled()
    sid = _school_id(principal)
    attachment = db.query(HomeworkAttachment).filter(
        HomeworkAttachment.id == attachment_id,
        HomeworkAttachment.school_id == sid,
        HomeworkAttachment.status == "ready",
    ).first()
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    submission, assignment = _submission_and_assignment(db, sid, attachment.submission_id)
    if principal.role == "student":
        student = _student_portal_student(principal, db)
        if submission.student_id != student.id:
            raise HTTPException(status_code=404, detail="Attachment not found")
    elif principal.role == "parent":
        _parent_student(principal, submission.student_id, db)
    elif principal.role == "teacher":
        if assignment.created_by_user_id != principal.user_id:
            raise HTTPException(status_code=404, detail="Attachment not found")
        require_teacher_class(db, principal, sid, assignment.class_name)
    elif principal.role not in {"owner", "headmaster"}:
        raise HTTPException(status_code=403, detail="Role cannot download attachments")
    try:
        signed_url = create_download_url(attachment.object_path, expires_in=300)
    except StorageOperationError:
        raise HTTPException(status_code=503, detail="Private file storage is unavailable") from None
    write_audit(
        db, principal, "homework.attachment.download_url", "homework_attachment",
        attachment.id, {"submission_id": submission.id}, school_id=sid,
    )
    return {"download_url": signed_url, "expires_in_seconds": 300}
