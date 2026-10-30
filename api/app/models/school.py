import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class School(Base):
    __tablename__ = "schools"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    province = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="onboarding")  # onboarding, live, suspended
    plan = Column(String(50), nullable=True, default="pilot")
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    users = relationship("User", back_populates="school", foreign_keys="User.school_id")
