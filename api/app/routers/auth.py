import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps_supabase import get_supabase_principal, SupabasePrincipal
from app.config import settings
from sqlalchemy import text

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/bootstrap-admin")
def bootstrap_first_admin(
    setup_token: str = Header(default="", alias="X-Chikoro-Bootstrap-Token"),
    db: Session = Depends(get_db),
):
    """Link the pre-existing platform admin to an already verified Supabase identity.

    This endpoint never creates users or sends invitations. The Auth identity
    must already exist and have a confirmed email matching the local admin.
    """
    configured_token = settings.admin_bootstrap_token
    if not configured_token or len(configured_token) < 32:
        raise HTTPException(status_code=503, detail="Administrator bootstrap is not configured")
    if not setup_token or not hmac.compare_digest(setup_token, configured_token):
        raise HTTPException(status_code=401, detail="Invalid bootstrap credentials")

    db.execute(text("LOCK TABLE public.profiles IN EXCLUSIVE MODE"))
    profile_count = db.execute(text("SELECT count(*) FROM public.profiles")).scalar_one()
    if profile_count:
        raise HTTPException(status_code=409, detail="Bootstrap is closed because a profile already exists")

    admins = db.execute(text("""
        SELECT id, email, role, school_id, is_active, is_admin
        FROM public.users
        WHERE is_admin = true AND role = 'admin' AND is_active = true AND school_id IS NULL
        ORDER BY id
        LIMIT 2
    """)).mappings().all()
    if len(admins) != 1 or not admins[0]["email"]:
        raise HTTPException(status_code=409, detail="A single active platform administrator with an email is required")
    admin = admins[0]

    auth_user = db.execute(text("""
        SELECT id
        FROM auth.users
        WHERE lower(email) = lower(:email)
          AND email_confirmed_at IS NOT NULL
        LIMIT 2
    """), {"email": admin["email"]}).all()
    if len(auth_user) != 1:
        raise HTTPException(status_code=409, detail="Create and verify the matching administrator account in Supabase Auth first")

    result = db.execute(text("""
        INSERT INTO public.profiles
            (id, local_user_id, role, school_id, is_active, created_at, updated_at)
        VALUES
            (CAST(:auth_id AS uuid), :local_user_id, 'admin', NULL, true, now(), now())
        ON CONFLICT DO NOTHING
    """), {"auth_id": str(auth_user[0][0]), "local_user_id": admin["id"]})
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Administrator identity is already linked")
    db.commit()
    return {"message": "The verified platform administrator identity has been linked. You can now sign in."}


@router.post("/login", status_code=status.HTTP_410_GONE)
def legacy_login_disabled():
    """Local-password login is retired; all users authenticate through Supabase Auth."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Local-password login is disabled. Sign in through the Chikoro Digital Supabase Auth flow.",
    )


@router.get("/me", status_code=status.HTTP_410_GONE)
def legacy_me_disabled():
    """Legacy local JWT identity endpoint is retired."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Legacy sessions are no longer accepted. Sign in again through Supabase Auth.",
    )


@router.get("/supabase/me")
def supabase_me(principal: SupabasePrincipal = Depends(get_supabase_principal)):
    """Return the server-resolved identity for a verified Supabase session."""
    return {
        "auth_user_id": str(principal.auth_user_id),
        "id": principal.user_id,
        "school_id": principal.school_id,
        "role": principal.role,
        "is_admin": principal.is_admin,
    }
