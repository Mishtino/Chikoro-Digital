from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint, Column, Date, DateTime, ForeignKey, ForeignKeyConstraint,
    Index, Integer, String, Text, UniqueConstraint,
)

from app.database import Base


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    term_id = Column(Integer, nullable=True, index=True)
    class_name = Column(String(40), nullable=False)
    attendance_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    recorded_by_user_id = Column(Integer, nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    __table_args__ = (
        UniqueConstraint("school_id", "class_name", "attendance_date", name="uq_attendance_session_school_class_date"),
        UniqueConstraint("school_id", "id", name="uq_attendance_sessions_school_id_id"),
        ForeignKeyConstraint(["school_id", "term_id"], ["terms.school_id", "terms.id"], name="fk_attendance_sessions_school_term"),
        ForeignKeyConstraint(["school_id", "recorded_by_user_id"], ["users.school_id", "users.id"], name="fk_attendance_sessions_school_actor"),
        CheckConstraint("status IN ('draft', 'submitted')", name="ck_attendance_session_status"),
        CheckConstraint("length(trim(class_name)) > 0", name="ck_attendance_class_name_nonempty"),
        Index("ix_attendance_sessions_school_date", "school_id", "attendance_date"),
    )


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    session_id = Column(Integer, nullable=False, index=True)
    student_id = Column(Integer, nullable=False, index=True)
    status = Column(String(20), nullable=False)
    note = Column(Text, nullable=True)
    marked_by_user_id = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_attendance_record_session_student"),
        ForeignKeyConstraint(["school_id", "session_id"], ["attendance_sessions.school_id", "attendance_sessions.id"], name="fk_attendance_records_school_session"),
        ForeignKeyConstraint(["school_id", "student_id"], ["students.school_id", "students.id"], name="fk_attendance_records_school_student"),
        ForeignKeyConstraint(["school_id", "marked_by_user_id"], ["users.school_id", "users.id"], name="fk_attendance_records_school_actor"),
        CheckConstraint("status IN ('present', 'absent', 'late', 'excused')", name="ck_attendance_record_status"),
        Index("ix_attendance_records_school_student", "school_id", "student_id"),
    )
