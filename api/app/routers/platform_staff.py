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
from app.models.user import User
from app.services.auth import hash_password
from app.services.supabase_admin import (
    SupabaseAdminError,
    delete_auth_user,
    invite_auth_user,
)

router = APIRouter(prefix="/platform/staff", tags=["platform-staff"])
STAFF_ROLES = {"vortex_support", "vortex_auditor", "vortex_billing"}


class StaffInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=5, max_length=255)
    full_name: str = Field(min_length=2, max_length=200)
    role: Literal["vortex_support", "vortex_auditor", "vortex_billing"]

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


@router.get("")
def list_platform_staff(
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    if not principal.is_platform_admin:
        raise HTTPException(status_code=403, detail="Vortex platform administrator access required")
    rows = db.execute(text("""
        SELECT p.id AS auth_user_id, u.email, u.full_name, p.role, p.is_active
        FROM public.profiles AS p
        JOIN public.users AS u ON u.id = p.local_user_id
        WHERE p.school_id IS NULL
          AND p.role IN ('vortex_admin', 'vortex_support', 'vortex_auditor', 'vortex_billing')
        ORDER BY u.email
    """)).mappings().all()
    return [dict(row) for row in rows]


@router.post("/invitations", status_code=status.HTTP_201_CREATED)
def invite_platform_staff(
    payload: StaffInviteRequest,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    if not principal.is_platform_admin:
        raise HTTPException(status_code=403, detail="Vortex platform administrator access required")
    if not (settings.supabase_secret_key or "").strip():
        raise HTTPException(status_code=503, detail="Platform staff invitations are not configured")
    if db.query(User).filter(func.lower(User.email) == payload.email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    try:
        auth_user_id = invite_auth_user(payload.email, payload.full_name)
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Platform staff invitations are not configured")
    except SupabaseAdminError as exc:
        if exc.status_code in {400, 409, 422}:
            raise HTTPException(status_code=409, detail="This email cannot be invited; it may already have an Auth account")
        raise HTTPException(status_code=502, detail="Supabase could not process the invitation")

    local_user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(secrets.token_urlsafe(48)),
        role=payload.role,
        school_id=None,
        is_active=True,
        is_admin=False,
    )
    try:
        db.add(local_user)
        db.flush()
        db.execute(text("""
            INSERT INTO public.profiles
                (id, local_user_id, role, school_id, is_active, created_at, updated_at)
            VALUES
                (CAST(:auth_id AS uuid), :local_user_id, :role, NULL, true, now(), now())
        """), {
            "auth_id": auth_user_id,
            "local_user_id": local_user.id,
            "role": payload.role,
        })
        db.add(AuditLog(
            school_id=None,
            actor_user_id=principal.user_id,
            action="platform.staff.invited",
            entity_type="platform_staff",
            entity_id=auth_user_id,
            details={"role": payload.role},
        ))
        db.commit()
    except Exception:
        db.rollback()
        try:
            delete_auth_user(auth_user_id)
        except (SupabaseAdminError, RuntimeError):
            # The invite must be invalidated if local linking fails. Alert via
            # server logs/monitoring without exposing the secret or invite URL.
            import logging
            logging.getLogger("chikoro.security").exception(
                "platform_staff_auth_compensation_failed auth_user_id=%s",
                auth_user_id,
            )
        raise HTTPException(
            status_code=503,
            detail="The invitation could not be linked to Chikoro. The operation was rolled back.",
        )

    return {
        "message": "Invitation sent. The staff member must accept the email invitation before signing in.",
        "email": payload.email,
        "role": payload.role,
    }
