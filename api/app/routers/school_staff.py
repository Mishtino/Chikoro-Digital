import logging
import re
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.models.audit import AuditLog
from app.models.school import School
from app.models.user import User
from app.services.auth import hash_password
from app.services.school_staff_access import authorize_school_staff_write
from app.services.school_staff_onboarding import (
    link_pending_staff_profile,
    school_staff_role_schema_ready,
)
from app.services.supabase_admin import SupabaseAdminError, delete_auth_user, invite_auth_user

logger = logging.getLogger("chikoro.security")
router = APIRouter(prefix="/users", tags=["school-staff"])

class SchoolStaffInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=5, max_length=255)
    full_name: str = Field(min_length=2, max_length=200)
    role: Literal["headmaster", "bursar", "teacher"]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("full_name")
    @classmethod
    def normalize_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Full name cannot be empty")
        return value


@router.post("/invitations", status_code=status.HTTP_201_CREATED)
def invite_school_staff(
    payload: SchoolStaffInviteRequest,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    school_id = principal.school_id
    if school_id is None:
        raise HTTPException(status_code=403, detail="School administrator access required")
    authorize_school_staff_write(principal, school_id, payload.role)

    if not settings.school_staff_invitations_enabled:
        raise HTTPException(status_code=503, detail="School staff invitations are not enabled")
    if not school_staff_role_schema_ready(db):
        raise HTTPException(status_code=503, detail="The validated staff-role migration is required")
    if not (settings.supabase_secret_key or "").strip():
        raise HTTPException(status_code=503, detail="School staff invitations are not configured")

    school = db.query(School).filter(School.id == school_id).with_for_update().first()
    if school is None or school.status != "live":
        raise HTTPException(status_code=409, detail="Staff invitations require an active school")
    if db.query(User).filter(func.lower(User.email) == payload.email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    try:
        auth_user_id = invite_auth_user(payload.email, payload.full_name)
    except RuntimeError:
        raise HTTPException(status_code=503, detail="School staff invitations are not configured")
    except SupabaseAdminError as exc:
        if exc.status_code in {400, 409, 422}:
            raise HTTPException(status_code=409, detail="This email cannot be invited; it may already have an Auth account")
        raise HTTPException(status_code=502, detail="Supabase could not process the invitation")

    local_user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(secrets.token_urlsafe(48)),
        role=payload.role,
        school_id=school_id,
        is_active=False,
        is_admin=False,
    )
    try:
        db.add(local_user)
        db.flush()
        link_pending_staff_profile(db, auth_user_id, local_user.id, payload.role, school_id)
        db.add(AuditLog(
            school_id=school_id,
            actor_user_id=principal.user_id,
            action="school.staff.invited",
            entity_type="school_staff",
            entity_id=auth_user_id,
            details={"role": payload.role, "email": payload.email, "activation_pending": True},
        ))
        db.commit()
    except Exception:
        db.rollback()
        try:
            delete_auth_user(auth_user_id)
        except (SupabaseAdminError, RuntimeError):
            logger.exception("school_staff_invite_compensation_failed auth_user_id=%s", auth_user_id)
        raise HTTPException(
            status_code=503,
            detail="The invitation could not be linked to the school account. The operation was rolled back.",
        )

    return {
        "message": "Invitation sent. Access remains disabled until the invitee verifies their email and activates the account.",
        "email": payload.email,
        "role": payload.role,
        "school_id": school_id,
        "activation_pending": True,
    }
