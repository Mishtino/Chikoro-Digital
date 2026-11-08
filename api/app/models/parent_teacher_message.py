from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint,
    Index, Integer, String, Text, UniqueConstraint,
)

from app.database import Base


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ParentTeacherConversation(Base):
    __tablename__ = "parent_teacher_conversations"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    student_id = Column(Integer, nullable=False, index=True)
    parent_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    teacher_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subject = Column(String(160), nullable=False)
    status = Column(String(20), nullable=False, default="open")
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    __table_args__ = (
        UniqueConstraint("school_id", "id", name="uq_parent_teacher_conversations_school_id"),
        ForeignKeyConstraint(
            ["school_id", "parent_user_id"], ["users.school_id", "users.id"],
            name="fk_parent_teacher_conversation_school_parent",
        ),
        ForeignKeyConstraint(
            ["school_id", "teacher_user_id"], ["users.school_id", "users.id"],
            name="fk_parent_teacher_conversation_school_teacher",
        ),
        ForeignKeyConstraint(
            ["school_id", "student_id"],
            ["students.school_id", "students.id"],
            name="fk_parent_teacher_conversation_school_student",
        ),
        UniqueConstraint(
            "school_id", "student_id", "parent_user_id", "teacher_user_id",
            "subject", name="uq_parent_teacher_conversation_participants_subject",
        ),
        CheckConstraint("status IN ('open', 'closed')", name="ck_parent_teacher_conversation_status"),
        CheckConstraint("length(trim(subject)) > 0", name="ck_parent_teacher_conversation_subject"),
        Index("ix_parent_teacher_conversations_school_updated", "school_id", "updated_at"),
    )


class ParentTeacherMessage(Base):
    __tablename__ = "parent_teacher_messages"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    conversation_id = Column(Integer, nullable=False, index=True)
    sender_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["school_id", "conversation_id"],
            ["parent_teacher_conversations.school_id", "parent_teacher_conversations.id"],
            name="fk_parent_teacher_message_school_conversation",
        ),
        ForeignKeyConstraint(
            ["school_id", "sender_user_id"], ["users.school_id", "users.id"],
            name="fk_parent_teacher_message_school_sender",
        ),
        CheckConstraint("length(trim(body)) > 0", name="ck_parent_teacher_message_body"),
        UniqueConstraint("school_id", "id", name="uq_parent_teacher_messages_school_id_id"),
        Index("ix_parent_teacher_messages_conversation_created", "conversation_id", "created_at"),
    )
