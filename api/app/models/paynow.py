from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, ForeignKey, Numeric, Boolean, Text

from app.database import Base


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PaynowAttempt(Base):
    __tablename__ = "paynow_attempts"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True, index=True)
    reference = Column(String(120), nullable=True, index=True)
    amount = Column(Numeric(12, 2), nullable=False)

    currency = Column(String(3), nullable=False, default="USD")
    status = Column(String(20), nullable=False, default="created")  # created, sent, paid, failed, cancelled
    poll_url = Column(Text, nullable=True)
    paynow_reference = Column(String(120), nullable=True)
    browser_url = Column(Text, nullable=True)
    hash_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
