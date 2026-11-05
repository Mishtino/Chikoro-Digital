from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint,
    Index, Integer, String, Time, UniqueConstraint,
)

from app.database import Base


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimetableEntry(Base):
    __tablename__ = "timetable_entries"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    term_id = Column(Integer, nullable=False, index=True)
    subject_id = Column(Integer, nullable=False, index=True)
    teacher_user_id = Column(Integer, nullable=True, index=True)
    class_name = Column(String(40), nullable=False)
    day_of_week = Column(Integer, nullable=False)
    period_number = Column(Integer, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    room = Column(String(80), nullable=True)
    created_by_user_id = Column(Integer, nullable=False
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    __table_args__ = (
        UniqueConstraint("school_id", "term_id", "class_name", "day_of_week", "period_number", name="uq_timetable_class_day_period"),
        ForeignKeyConstraint(["school_id", "term_id"], ["terms.school_id", "terms.id"], name="fk_timetable_school_term"),
        ForeignKeyConstraint(["school_id", "subject_id"], ["subjects.school_id", "subjects.id"], name="fk_timetable_school_subject"),
        ForeignKeyConstraint(["school_id", "teacher_user_id"], ["users.school_id", "users.id"], name="fk_timetable_school_teacher"),
        ForeignKeyConstraint(["school_id", "created_by_user_id"], ["users.school_id", "users.id"], name="fk_timetable_school_creator"),
        CheckConstraint("day_of_week BETWEEN 1 AND 7", name="ck_timetable_day_of_week"),
        CheckConstraint("period_number > 0", name="ck_timetable_period_positive"),
        CheckConstraint("start_time < end_time", name="ck_timetable_time_range"),
        CheckConstraint("length(trim(class_name)) > 0", name="ck_timetable_class_name_nonempty"),
        Index("ix_timetable_school_day_class", "school_id", "day_of_week", "class_name"),
    )
