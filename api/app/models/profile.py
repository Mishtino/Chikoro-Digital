from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.types import Uuid

from app.database import Base


class Profile(Base):
    """Application authorization profile mapped one-to-one to Supabase Auth."""

    __tablename__ = "profiles"

    id = Column(Uuid(as_uuid=False), primary_key=True)
    local_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), unique=True, nullable=True)
    role = Column(String(50), nullable=False, default="pending")
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
