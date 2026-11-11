"""Classroom scheduling metadata. No video provider credentials stored here."""
from datetime import datetime, timezone

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Column, DateTime,
    ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint)
from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class ClassroomSettings(Base):
    __tablename__ = "classroom_settings"
    school_id = Column(Integer, ForeignKey("schools.id"), primary_key=True)
    embedded_enabled = Column(Boolean, nullable=False, default=False)
    external_enabled = Column(Boolean, nullable=False, default=False)
    recordings_enabled = Column(Boolean, nullable=False, default=False)
    updated_by_user_id = Column(Integer)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (ForeignKeyConstraint(["school_id","updated_by_user_id"],
        ["users.school_id","users.id"], name="fk_classroom_settings_actor"),)


class ClassroomSession(Base):
    __tablename__ = "classroom_sessions"
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    class_name = Column(String(80), nullable=False)
    host_user_id = Column(Integer, nullable=False)
    created_by_user_id = Column(Integer, nullable=False)
    mode = Column(String(16), nullable=False)
    provider = Column(String(32), nullable=False)
    provider_reference = Column(Text)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(16), nullable=False, default="scheduled")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        UniqueConstraint("school_id","id",name="uq_classroom_sessions_school_id_id"),
        ForeignKeyConstraint(["school_id","host_user_id"],["users.school_id","users.id"],name="fk_classroom_host"),
        ForeignKeyConstraint(["school_id","created_by_user_id"],["users.school_id","users.id"],name="fk_classroom_creator"),
        CheckConstraint("length(trim(class_name)) > 0",name="ck_classroom_class_nonempty"),
        CheckConstraint("starts_at < ends_at",name="ck_classroom_duration"),
        CheckConstraint("mode IN ('embedded','external')",name="ck_classroom_mode"),
        CheckConstraint("status IN ('scheduled','live','ended','cancelled')",name="ck_classroom_status"),
        Index("ix_classroom_sessions_schedule","school_id","starts_at"),
    )
