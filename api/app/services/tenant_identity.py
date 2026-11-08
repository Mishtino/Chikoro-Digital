"""Opt-in identity bootstrap for staging; production dependencies are unchanged."""
from uuid import UUID

from app.services.supabase_auth import resolve_profile, verify_supabase_access_token
from app.tenant_context import TenantContext, TenantContextSession


def resolve_tenant_identity(db: TenantContextSession, access_token: str) -> dict:
    """Verify the token, resolve the live profile, then attach trusted context.

    No school/role is copied from the JWT or caller-provided metadata. The
    existing resolver validates active state and profile/local-account parity.
    Caller owns the Session lifetime and must close it after the request.
    """
    if not isinstance(db, TenantContextSession):
        raise TypeError("TenantContextSession required")
    # A second identity must never inherit an earlier request's transaction.
    if db.in_transaction() or db.info.get("tenant_context") or db.info.get("verified_subject"):
        raise RuntimeError("Identity resolution requires a fresh Session")
    try:
        claims = verify_supabase_access_token(access_token)
        subject = UUID(claims["sub"])
        db.begin_identity_resolution(subject)
        profile = resolve_profile(db, claims)
        db.complete_identity_resolution(TenantContext(
            auth_user_id=subject,
            local_user_id=profile["local_user_id"],
            school_id=profile["school_id"],
            role=profile["role"],
        ))
        return profile
    except Exception:
        db.reject_identity_resolution()
        raise
