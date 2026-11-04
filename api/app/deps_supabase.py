"""Supabase Auth dependencies; adopt per-router after integration tests."""
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.supabase_auth import verify_supabase_access_token, resolve_profile

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class SupabasePrincipal:
    auth_user_id: UUID
    user_id: int
    school_id: Optional[int]
    role: str
    is_admin: bool


def get_supabase_principal(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> SupabasePrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer access token required")
    claims = verify_supabase_access_token(credentials.credentials)
    profile = resolve_profile(db, claims)
    return SupabasePrincipal(
        auth_user_id=UUID(claims["sub"]),
        user_id=profile["local_user_id"],
        school_id=profile["school_id"],
        role=profile["role"],
        is_admin=bool(profile["is_admin"]),
    )


def require_supabase_roles(*roles: str):
    allowed = frozenset(roles)

    def dependency(principal: SupabasePrincipal = Depends(get_supabase_principal)):
        if principal.role not in allowed and not principal.is_admin:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return principal

    return dependency
