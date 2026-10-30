from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, ForeignKey, Numeric, Boolean, Date, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    term_id = Column(Integer, ForeignKey("terms.id"), nullable=True, index=True)
    invoice_number = Column(String(40), nullable=False, index=True)
    currency = Column(String(3), nullable=False, default="USD")
    total = Column(Numeric(12, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="issued")  # draft, issued, paid, void
    due_date = Column(Date, nullable=True)
    issued_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    voided_at = Column(DateTime(timezone=True), nullable=True)
    void_reason = Column(String(255), nullable=True)

    __table_args__ = (UniqueConstraint("school_id", "invoice_number", name="uq_invoice_number_per_school"),)


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    description = Column(String(255), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    method = Column(String(40), nullable=False, default="manual")  # manual, cash, bank, mobile, paynow
    reference = Column(String(120), nullable=True)
    received_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    received_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    voided = Column(Boolean, default=False, nullable=False)
    voided_at = Column(DateTime(timezone=True), nullable=True)
    void_reason = Column(String(255), nullable=True)


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False, index=True)
    receipt_number = Column(String(40), nullable=False, index=True)
    issued_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)

    __table_args__ = (UniqueConstraint("school_id", "receipt_number", name="uq_receipt_number_per_school"),)
