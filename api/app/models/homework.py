from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint,
    Index, Integer, Numeric, String, Text, UniqueConstraint,
)

from app.database import Base


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class HomeworkAssignment(Base):
    __tablename__ = "homework_assignments"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    class_name = Column(String(40), nullable=False)
    subject_id = Column(Integer, nullable=False, index=True)
    term_id = Column(Integer, nullable=True, index=True)
    title = Column(String(160), nullable=False)
    instructions = Column(Text, nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="draft")
    created_by_user_id = Column(Integer, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    __table_args__ = (
        UniqueConstraint("school_id", "id", name="uq_homework_assignments_school_id_id"),
        ForeignKeyConstraint(["school_id", "subject_id"], ["subjects.school_id", "subjects.id"], name="fk_homework_school_subject"),
        ForeignKeyConstraint(["school_id", "term_id"], ["terms.school_id", "terms.id"], name="fk_homework_school_term"),
        ForeignKeyConstraint(["school_id", "created_by_user_id"], ["users.school_id", "users.id"], name="fk_homework_school_creator"),
        CheckConstraint("status IN ('draft', 'published', 'closed')", name="ck_homework_assignment_status"),
        CheckConstraint("length(trim(class_name)) > 0", name="ck_homework_class_nonempty"),
        CheckConstraint("length(trim(title)) > 0", name="ck_homework_title_nonempty"),
        CheckConstraint("length(trim(instructions)) > 0", name="ck_homework_instructions_nonempty"),
        Index("ix_homework_school_class_due", "school_id", "class_name", "due_at"),
    )


class HomeworkSubmission(Base):
    __tablename__ = "homework_submissions"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    assignment_id = Column(Integer, nullable=False, index=True)
    student_id = Column(Integer, nullable=False, index=True)
    answer_text = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="submitted")
    submitted_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    feedback = Column(Text, nullable=True)
    score = Column(Numeric(7, 2), nullable=True)
    marked_by_user_id = Column(Integer, nullable=True)
    marked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    __table_args__ = (
        UniqueConstraint("school_id", "assignment_id", "student_id", name="uq_homework_submission_once"),
        ForeignKeyConstraint(["school_id", "assignment_id"], ["homework_assignments.school_id", "homework_assignments.id"], name="fk_homework_submission_school_assignment"),
        ForeignKeyConstraint(["school_id", "student_id"], ["students.school_id", "students.id"], name="fk_homework_submission_school_student"),
        ForeignKeyConstraint(["school_id", "marked_by_user_id"], ["users.school_id", "users.id"], name="fk_homework_submission_school_marker"),
        CheckConstraint("status IN ('submitted', 'marked')", name="ck_homework_submission_status"),
        CheckConstraint("length(trim(answer_text)) > 0", name="ck_homework_answer_nonempty"),
        CheckConstraint("score IS NULL OR score >= 0", name="ck_homework_score_nonnegative"),
        Index("ix_homework_submissions_school_student", "school_id", "student_id"),
    )


class HomeworkAttachment(Base):
    __tablename__ = "homework_attachments"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    submission_id = Column(Integer, nullable=False, index=True)
    uploaded_by_user_id = Column(Integer, nullable=False)
    object_path = Column(String(500), nullable=False, unique=True)
    original_filename = Column(String(255), nullable=False)
    content_type = Column(String(120), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["school_id", "submission_id"],
            ["homework_submissions.school_id", "homework_submissions.id"],
            name="fk_homework_attachment_school_submission",
        ),
        ForeignKeyConstraint(
            ["school_id", "uploaded_by_user_id"],
            ["users.school_id", "users.id"],
            name="fk_homework_attachment_school_uploader",
        ),
        CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="ck_homework_attachment_size"),
        CheckConstraint("status IN ('pending', 'ready')", name="ck_homework_attachment_status"),
        UniqueConstraint("school_id", "id", name="uq_homework_attachments_school_id_id"),
        Index("ix_homework_attachments_school_submission", "school_id", "submission_id"),
    )
