"""Verify Supabase access tokens and resolve trusted application profiles.

Only asymmetric JWTs published by the project's JWKS endpoint are accepted.
Authorization data is loaded from public.profiles, never from user-editable
JWT user_metadata. The caller supplies a SQLAlchemy session.
"""
from __future__ import annotations

import json
import time
from functools import lru_cache
from urllib.error import URLError
from urllib.request import Request, urlopen

from jose import JWTError, jwt
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings


JWKS_TTL_SECONDS = 300
JWKS_TIMEOUT_SECONDS = 4


@lru_cache(maxsize=4)
def _jwks_cache_key(url: str, bucket: int) -> str:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=JWKS_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload.get("keys"), list):
        raise ValueError("Invalid JWKS document")
    return json.dumps(payload)


def _get_jwks() -> dict:
    base = (settings.supabase_url or "").rstrip("/")
    if not base:
        raise RuntimeError("SUPABASE_URL is not configured")
    url = f"{base}/auth/v1/.well-known/jwks.json"
    return json.loads(_jwks_cache_key(url, int(time.time() // JWKS_TTL_SECONDS)))


def verify_supabase_access_token(token: str) -> dict:
    """Return verified claims or raise a generic 401 without leaking details."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        header = jwt.get_unverified_header(token)
        # Supabase asymmetric signing keys only. Reject alg=none and symmetric
        # algorithms; never trust a token-provided key URL.
        if header.get("alg") not in {"ES256", "RS256"} or not header.get("kid"):
            raise JWTError("Unsupported signing algorithm")
        jwks = _get_jwks()
        key = next((item for item in jwks["keys"] if item.get("kid") == header["kid"]), None)
        if key is None:
            # Refresh once for key rotation.
            _jwks_cache_key.cache_clear()
            jwks = _get_jwks()
            key = next((item for item in jwks["keys"] if item.get("kid") == header["kid"]), None)
        if key is None:
            raise JWTError("Unknown signing key")
        claims = jwt.decode(
            token,
            key,
            algorithms=[header["alg"]],
            audience="authenticated",
            issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1",
            options={"verify_exp": True, "verify_aud": True, "verify_iss": True},
        )
        if claims.get("role") != "authenticated" or not claims.get("sub"):
            raise JWTError("Unexpected token claims")
        return claims
    except (JWTError, ValueError, KeyError, TypeError, URLError, OSError, RuntimeError):
        raise unauthorized


def resolve_profile(db: Session, claims: dict) -> dict:
    """Resolve Auth UUID to an active, trusted local profile."""
    row = db.execute(
        text("""
            SELECT p.id, p.local_user_id, p.role, p.school_id, p.is_active,
                   u.role AS local_user_role, u.school_id AS local_school_id,
                   u.is_admin, u.is_active AS local_user_is_active
            FROM public.profiles AS p
            LEFT JOIN public.users AS u ON u.id = p.local_user_id
            WHERE p.id = :auth_id
            LIMIT 1
        """),
        {"auth_id": claims["sub"]},
    ).mappings().first()
    if (not row or not row["is_active"] or row["local_user_id"] is None
            or not row["local_user_is_active"]):
        raise HTTPException(status_code=403, detail="Account is not activated for Chikoro Digital")

    # The bridge must not become a way to elevate a local account or move it
    # into another school's tenant. Vortex administrators are the sole
    # intentional role exception and must be marked admin in public.users.
    if bool(row["is_admin"]):
        # Global privilege is valid only for the dedicated Vortex role with no tenant.
        role_matches = (
            row["role"] == "vortex_admin"
            and row["local_user_role"] == "admin"
            and row["school_id"] is None
            and row["local_school_id"] is None
        )
    else:
        role_matches = row["role"] == row["local_user_role"]
    school_matches = row["school_id"] == row["local_school_id"]
    if not role_matches or not school_matches:
        raise HTTPException(status_code=403, detail="Account identity does not match its school record")

    return dict(row)
