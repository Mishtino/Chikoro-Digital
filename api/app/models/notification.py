from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, ForeignKey, JSON, Text, Boolean

from app.database import Base


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=True, index=True)
    dedupe_key = Column(String(255), unique=True, nullable=False, index=True)
    channel = Column(String(40), nullable=False)  # inapp, email, sms, whatsapp
    recipient = Column(String(255), nullable=False)
    payload = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="queued")  # queued, sent, failed
    attempts = Column(Integer, default=0, nullable=False)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
