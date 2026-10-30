from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, ForeignKey, Numeric, Boolean, JSON, Text

from app.database import Base


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    code = Column(String(40), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    term_id = Column(Integer, ForeignKey("terms.id"), nullable=True, index=True)
    name = Column(String(120), nullable=False)
    weight = Column(Numeric(5, 2), nullable=False, default=1)
    max_score = Column(Numeric(6, 2), nullable=False, default=100)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)


class Mark(Base):
    __tablename__ = "marks"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False, index=True)
    score = Column(Numeric(6, 2), nullable=False)
    status = Column(String(20), nullable=False, default="draft")  # draft, approved, published
    published_at = Column(DateTime(timezone=True), nullable=True)
    entered_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
