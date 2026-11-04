from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.types import Uuid

from app.database import Base


class GuardianLink(Base):
    """A school-verified relationship between an Auth profile and a student contact."""

    __tablename__ = "guardian_links"

    id = Column(Uuid(as_uuid=False), primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    profile_id = Column(Uuid(as_uuid=False), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=False)
    verified_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("profile_id", "contact_id", name="guardian_links_profile_contact_unique"),)
