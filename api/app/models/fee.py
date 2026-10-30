from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, ForeignKey, Numeric, Date, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship

from app.database import Base


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Term(Base):
    __tablename__ = "terms"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    academic_year = Column(String(20), nullable=False)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    is_current = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)


class FeeItem(Base):
    __tablename__ = "fee_items"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    applies_to_form = Column(String(40), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)


class FeeStructure(Base):
    __tablename__ = "fee_structures"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    term_id = Column(Integer, ForeignKey("terms.id"), nullable=False, index=True)
    form = Column(String(40), nullable=True)
    name = Column(String(120), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)


class FeeStructureItem(Base):
    __tablename__ = "fee_structure_items"

    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    fee_structure_id = Column(Integer, ForeignKey("fee_structures.id"), nullable=False, index=True)
    fee_item_id = Column(Integer, ForeignKey("fee_items.id"), nullable=True)
    description = Column(String(200), nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
