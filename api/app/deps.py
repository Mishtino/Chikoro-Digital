from dataclasses import dataclass
from typing import Optional
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.profile import Profile
from app.models.user import User
from app.services.auth import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@dataclass
class Principal:
    user_id: int
    auth_user_id: str
    school_id: Optional[int]
    role: str
    is_admin: bool


def get_current_principal(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Principal:
    """Validate Supabase Auth in production and resolve permissions from profiles.

    A legacy-token compatibility path is deliberately limited to non-production
    environments to keep local development and existing test fixtures usable.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired Supabase session",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if settings.env != "production":
        try:
            payload = decode_token(token)
            user = db.get(User, int(payload.get("sub")))
            if user and user.is_active:
                return Principal(user.id, "", user.school_id, user.role, user.is_admin)
        except Exception:
            pass

    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(status_code=503, detail="Supabase Auth verification is not configured")

    try:
        response = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}"},
            timeout=5.0,
        )
        if response.status_code != 200:
            raise credentials_exception
        auth_user_id = str(UUID(response.json()["id"]))
    except HTTPException:
        raise
    except Exception:
        raise credentials_exception

    profile = db.get(Profile, auth_user_id)
    if profile is None or not profile.is_active or profile.local_user_id is None:
        raise HTTPException(status_code=403, detail="Account is not provisioned. Contact your school administrator.")

    user = db.get(User, profile.local_user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    return Principal(
        user_id=user.id,
        auth_user_id=auth_user_id,
        school_id=profile.school_id,
        role=profile.role,
        is_admin=profile.role == "admin",
    )


def require_admin(principal: Principal = Depends(get_current_principal)) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return principal


def require_school(principal: Principal = Depends(get_current_principal)) -> Principal:
    if principal.school_id is None and not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="School context required")
    return principal
