from typing import Optional
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_principal, Principal
from app.models.user import User
from app.models.student import Student
from app.schemas import auth as schemas
from app.services.auth import verify_password, create_access_token
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

    profile_count = db.execute(text("SELECT count(*) FROM public.profiles")).scalar_one()
    if profile_count:
        raise HTTPException(status_code=409, detail="Bootstrap is closed because a profile already exists")

    admins = db.execute(text("""
        SELECT id, email, role, school_id, is_active, is_admin
        FROM public.users
        WHERE is_admin = true AND role = 'admin' AND is_active = true
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

    db.execute(text("""
        INSERT INTO public.profiles
            (id, local_user_id, role, school_id, is_active, created_at, updated_at)
        VALUES
            (CAST(:auth_id AS uuid), :local_user_id, 'admin', NULL, true, now(), now())
    """), {"auth_id": str(auth_user[0][0]), "local_user_id": admin["id"]})
    db.commit()
    return {"message": "The verified platform administrator identity has been linked. You can now sign in."}


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    # allow students to log in with their student ID
    if user is None and "@" not in form.username:
        student = db.query(Student).filter(Student.student_number == form.username).first()
        if student and student.portal_user_id:
            user = db.get(User, student.portal_user_id)
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    # keep portal user name in sync with school records
    if user.role == "student":
        student = db.query(Student).filter(Student.portal_user_id == user.id).first()
        if student:
            user.full_name = f"{student.first_name} {student.last_name}"
            db.commit()
    token = create_access_token(str(user.id), user.school_id, user.role, user.is_admin)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
def me(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    user = db.get(User, principal.user_id)
    if user.role == "student":
        student = db.query(Student).filter(Student.portal_user_id == user.id).first()
        if student:
            user.full_name = f"{student.first_name} {student.last_name}"
            db.commit()
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "school_id": user.school_id,
        "is_admin": user.is_admin,
    }


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
