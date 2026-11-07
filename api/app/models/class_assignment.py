from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint,
    Index, Integer, String, UniqueConstraint,
)

from app.database import Base


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ClassTeacherAssignment(Base):
    __tablename__ = "class_teacher_assignments"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    class_name = Column(String(40), nullable=False)
    teacher_user_id = Column(Integer, nullable=False, index=True)
    assigned_by_user_id = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    __table_args__ = (
        UniqueConstraint("school_id", "class_name", "teacher_user_id", name="uq_class_teacher_assignment"),
        ForeignKeyConstraint(["school_id", "teacher_user_id"], ["users.school_id", "users.id"], name="fk_class_assignment_school_teacher"),
        ForeignKeyConstraint(["school_id", "assigned_by_user_id"], ["users.school_id", "users.id"], name="fk_class_assignment_school_actor"),
        CheckConstraint("length(trim(class_name)) > 0", name="ck_class_assignment_name_nonempty"),
        Index("ix_class_assignments_school_teacher_active", "school_id", "teacher_user_id", "is_active"),
    )
