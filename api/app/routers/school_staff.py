import logging
import re
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.models.audit import AuditLog
from app.models.school import School
from app.models.user import User
from app.services.auth import hash_password
from app.services.school_staff_access import (
    authorize_school_staff_role_change,
    authorize_school_staff_write,
    ensure_not_self_deactivation,
)
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

class SchoolStaffRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["headmaster", "bursar", "teacher"]


class SchoolStaffStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool


def _require_staff_lifecycle_ready(db: Session):
    if not settings.school_staff_lifecycle_enabled:
        raise HTTPException(status_code=503, detail="School staff lifecycle management is not enabled")
    if not school_staff_role_schema_ready(db):
        raise HTTPException(status_code=503, detail="The validated staff-role migration is required")


def _lock_linked_staff(db: Session, principal: SupabasePrincipal, user_id: int):
    if principal.school_id is None:
        raise HTTPException(status_code=403, detail="School administrator access required")
    target = (
        db.query(User)
        .filter(User.id == user_id, User.school_id == principal.school_id)
        .with_for_update()
        .first()
    )
    if target is None or target.is_admin or target.role not in {"headmaster", "bursar", "teacher"}:
        raise HTTPException(status_code=404, detail="Managed school staff account not found")
    profile = db.execute(text("""
        SELECT id, role, school_id, is_active
        FROM public.profiles
        WHERE local_user_id = :local_user_id
        FOR UPDATE
    """), {"local_user_id": target.id}).mappings().first()
    if (
        profile is None
        or profile["role"] != target.role
        or profile["school_id"] != principal.school_id
        or bool(profile["is_active"]) != bool(target.is_active)
    ):
        raise HTTPException(status_code=409, detail="Staff profile and school account are not consistently linked")
    return target, profile


@router.patch("/{user_id}/role")
def change_school_staff_role(
    user_id: int,
    payload: SchoolStaffRoleRequest,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    if principal.school_id is None:
        raise HTTPException(status_code=403, detail="School administrator access required")
    authorize_school_staff_role_change(principal, principal.school_id, payload.role)
    _require_staff_lifecycle_ready(db)
    if user_id == principal.user_id:
        raise HTTPException(status_code=409, detail="You cannot change your own school administrator role")
    target, profile = _lock_linked_staff(db, principal, user_id)
    if target.role == payload.role:
        return {"user_id": target.id, "role": target.role, "message": "No change required"}
    school = db.query(School).filter(School.id == principal.school_id).with_for_update().first()
    if school is None or school.status != "live":
        raise HTTPException(status_code=409, detail="Staff role changes require an active school")
    previous_role = target.role
    result = db.execute(text("""
        UPDATE public.profiles
        SET role = :new_role, updated_at = now()
        WHERE id = CAST(:auth_id AS uuid)
          AND role = :old_role AND school_id = :school_id
    """), {
        "auth_id": str(profile["id"]), "new_role": payload.role,
        "old_role": previous_role, "school_id": principal.school_id,
    })
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Staff role changed concurrently; refresh and try again")
    target.role = payload.role
    db.add(AuditLog(
        school_id=principal.school_id,
        actor_user_id=principal.user_id,
        action="school.staff.role_changed",
        entity_type="school_staff",
        entity_id=str(profile["id"]),
        details={"from_role": previous_role, "to_role": payload.role},
    ))
    db.commit()
    return {"user_id": target.id, "role": target.role, "message": "Staff role updated"}


@router.patch("/{user_id}/status")
def update_school_staff_status(
    user_id: int,
    payload: SchoolStaffStatusRequest,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    if principal.school_id is None:
        raise HTTPException(status_code=403, detail="School administrator access required")
    _require_staff_lifecycle_ready(db)
    target, profile = _lock_linked_staff(db, principal, user_id)
    authorize_school_staff_write(principal, principal.school_id, target.role)
    if not payload.is_active:
        ensure_not_self_deactivation(principal.user_id, target.id)
    if bool(target.is_active) == payload.is_active:
        return {"user_id": target.id, "is_active": target.is_active, "message": "No change required"}
    school = db.query(School).filter(School.id == principal.school_id).with_for_update().first()
    if school is None or (payload.is_active and school.status != "live"):
        raise HTTPException(status_code=409, detail="Staff activation requires an active school")
    result = db.execute(text("""
        UPDATE public.profiles
        SET is_active = :is_active, updated_at = now()
        WHERE id = CAST(:auth_id AS uuid)
          AND role = :role AND school_id = :school_id
          AND is_active = :previous_active
    """), {
        "auth_id": str(profile["id"]), "is_active": payload.is_active,
        "role": target.role, "school_id": principal.school_id,
        "previous_active": bool(target.is_active),
    })
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Staff status changed concurrently; refresh and try again")
    target.is_active = payload.is_active
    db.add(AuditLog(
        school_id=principal.school_id,
        actor_user_id=principal.user_id,
        action="school.staff.activated" if payload.is_active else "school.staff.deactivated",
        entity_type="school_staff",
        entity_id=str(profile["id"]),
        details={"role": target.role, "from_active": not payload.is_active, "to_active": payload.is_active},
    ))
    db.commit()
    return {"user_id": target.id, "is_active": target.is_active, "message": "Staff access enabled" if target.is_active else "Staff access disabled"}
