from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, ForeignKey, Numeric, Boolean, Date, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    student_number = Column(String(40), nullable=False, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    form = Column(String(40), nullable=True)  # grade/class
    status = Column(String(20), nullable=False, default="active")
    activation_pin_hash = Column(String(255), nullable=True)
    activation_expires_at = Column(DateTime(timezone=True), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    portal_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    __table_args__ = (UniqueConstraint("school_id", "student_number", name="uq_student_number_per_school"),)


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    relationship = Column(String(50), nullable=True)
    phone = Column(String(40), nullable=True)
    email = Column(String(255), nullable=True)
    is_primary = Column(Boolean, default=False, nullable=False)
    verified_phone = Column(Boolean, default=False, nullable=False)
    verified_email = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
