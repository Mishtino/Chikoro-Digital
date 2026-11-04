import hmac
import secrets
import hashlib

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.deps_supabase import get_supabase_principal, SupabasePrincipal, bearer
from app.config import settings
from sqlalchemy import text, func
from fastapi.security import HTTPAuthorizationCredentials
from app.models.user import User
from app.services.auth import hash_password
from app.services.ids import verify_pin
from app.services.supabase_auth import verify_supabase_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


class ParentActivationRequest(BaseModel):
    pin: str


class StudentActivationRequest(BaseModel):
    pin: str


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


@router.post("/parent/activate")
def activate_parent_account(
    payload: ParentActivationRequest,
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Supabase bearer token required")
    if len(payload.pin) != 8 or not payload.pin.isdigit():
        raise HTTPException(status_code=422, detail="Activation PIN must contain exactly eight digits")
    claims = verify_supabase_access_token(credentials.credentials)
    auth_id = claims["sub"]
    auth_user = db.execute(text("""
        SELECT email, email_confirmed_at
        FROM auth.users
        WHERE id = CAST(:auth_id AS uuid)
    """), {"auth_id": auth_id}).mappings().first()
    if not auth_user or not auth_user["email"] or auth_user["email_confirmed_at"] is None:
        raise HTTPException(status_code=403, detail="Verify your email address before activating the parent portal")

    email_hash = hashlib.sha256(auth_user["email"].lower().encode("utf-8")).hexdigest()
    failed_attempts = db.execute(text("""
        SELECT count(*) FROM public.audit_logs
        WHERE action = 'guardian.activation.failed'
          AND entity_type = 'guardian_email_hash'
          AND entity_id = :email_hash
          AND created_at > now() - interval '1 hour'
    """), {"email_hash": email_hash}).scalar_one()
    if failed_attempts >= 5:
        raise HTTPException(status_code=429, detail="Too many activation attempts. Ask your school to issue a fresh PIN later.")

    contacts = db.execute(text("""
        SELECT c.id, c.student_id, c.school_id, c.name, c.guardian_activation_pin_hash
        FROM public.contacts AS c
        JOIN public.students AS s
          ON s.id = c.student_id AND s.school_id = c.school_id
        WHERE lower(c.email) = lower(:email)
          AND c.guardian_activation_pin_hash IS NOT NULL
          AND c.guardian_activation_expires_at > now()
          AND c.guardian_activated_at IS NULL
          AND s.status = 'active'
    """), {"email": auth_user["email"]}).mappings().all()
    matches = [row for row in contacts if verify_pin(payload.pin, row["guardian_activation_pin_hash"])]
    if len(matches) != 1:
        db.execute(text("""
            INSERT INTO public.audit_logs (action, entity_type, entity_id, details, created_at)
            VALUES ('guardian.activation.failed', 'guardian_email_hash', :email_hash, '{}'::jsonb, now())
        """), {"email_hash": email_hash})
        db.commit()
        raise HTTPException(status_code=403, detail="Activation PIN is invalid, expired, or not uniquely assigned")
    contact = matches[0]

    local_user = db.query(User).filter(func.lower(User.email) == auth_user["email"].lower()).first()
    if local_user is None:
        local_user = User(
            email=auth_user["email"].lower(),
            full_name=contact["name"],
            password_hash=hash_password(secrets.token_urlsafe(48)),
            role="parent",
            school_id=contact["school_id"],
            is_active=True,
            is_admin=False,
        )
        db.add(local_user)
        db.flush()
    elif not local_user.is_active or local_user.role != "parent" or local_user.school_id != contact["school_id"]:
        raise HTTPException(status_code=409, detail="This email is already assigned to a different Chikoro account")

    existing_profile = db.execute(text("""
        SELECT local_user_id, role, school_id, is_active
        FROM public.profiles
        WHERE id = CAST(:auth_id AS uuid)
    """), {"auth_id": auth_id}).mappings().first()
    if existing_profile and (
        existing_profile["local_user_id"] != local_user.id
        or existing_profile["role"] != "parent"
        or existing_profile["school_id"] != contact["school_id"]
        or not existing_profile["is_active"]
    ):
        raise HTTPException(status_code=409, detail="This Supabase identity is already linked to another account")
    other_profile = db.execute(text("""
        SELECT id FROM public.profiles WHERE local_user_id = :local_user_id AND id <> CAST(:auth_id AS uuid) LIMIT 1
    """), {"local_user_id": local_user.id, "auth_id": auth_id}).first()
    if other_profile is not None:
        raise HTTPException(status_code=409, detail="This local account is already linked to another Supabase identity")
    if not existing_profile:
        db.execute(text("""
            INSERT INTO public.profiles
                (id, local_user_id, role, school_id, is_active, created_at, updated_at)
            VALUES
                (CAST(:auth_id AS uuid), :local_user_id, 'parent', :school_id, true, now(), now())
        """), {"auth_id": auth_id, "local_user_id": local_user.id, "school_id": contact["school_id"]})

    db.execute(text("""
        INSERT INTO public.guardian_links
            (profile_id, contact_id, school_id, is_active, verified_at, created_at)
        VALUES
            (CAST(:auth_id AS uuid), :contact_id, :school_id, true, now(), now())
        ON CONFLICT (profile_id, contact_id)
        DO UPDATE SET is_active = true, verified_at = now(), school_id = EXCLUDED.school_id
    """), {"auth_id": auth_id, "contact_id": contact["id"], "school_id": contact["school_id"]})
    db.execute(text("""
        UPDATE public.contacts
        SET guardian_activated_at = now(),
            guardian_activation_pin_hash = NULL,
            guardian_activation_expires_at = NULL,
            verified_email = true
        WHERE id = :contact_id AND school_id = :school_id
    """), {"contact_id": contact["id"], "school_id": contact["school_id"]})
    db.execute(text("""
        INSERT INTO public.audit_logs (school_id, actor_user_id, action, entity_type, entity_id, details, created_at)
        VALUES (:school_id, :user_id, 'guardian.activation.succeeded', 'guardian_contact', :contact_id, '{}'::jsonb, now())
    """), {"school_id": contact["school_id"], "user_id": local_user.id, "contact_id": str(contact["id"])})
    db.commit()
    return {"message": "Parent account activated and linked to the verified learner."}


@router.post("/student/activate")
def activate_student_account(
    payload: StudentActivationRequest,
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Supabase bearer token required")
    if len(payload.pin) != 8 or not payload.pin.isdigit():
        raise HTTPException(status_code=422, detail="Activation PIN must contain exactly eight digits")
    claims = verify_supabase_access_token(credentials.credentials)
    auth_id = claims["sub"]
    auth_user = db.execute(text("""
        SELECT email, email_confirmed_at
        FROM auth.users
        WHERE id = CAST(:auth_id AS uuid)
    """), {"auth_id": auth_id}).mappings().first()
    if not auth_user or not auth_user["email"] or auth_user["email_confirmed_at"] is None:
        raise HTTPException(status_code=403, detail="Verify your email address before activating the student portal")

    email_hash = hashlib.sha256(auth_user["email"].lower().encode("utf-8")).hexdigest()
    failed_attempts = db.execute(text("""
        SELECT count(*) FROM public.audit_logs
        WHERE action = 'student.activation.failed'
          AND entity_type = 'student_email_hash'
          AND entity_id = :email_hash
          AND created_at > now() - interval '1 hour'
    """), {"email_hash": email_hash}).scalar_one()
    if failed_attempts >= 5:
        raise HTTPException(status_code=429, detail="Too many activation attempts. Ask your school to issue a fresh PIN later.")

    local_user = db.query(User).filter(func.lower(User.email) == auth_user["email"].lower()).first()
    student = None
    if local_user and local_user.is_active and local_user.role == "student" and local_user.school_id is not None:
        candidates = db.query(Student).filter(
            Student.portal_user_id == local_user.id,
            Student.school_id == local_user.school_id,
            Student.status == "active",
            Student.activated_at.is_(None),
            Student.activation_pin_hash.isnot(None),
            Student.activation_expires_at > func.now(),
        ).all()
        matches = [item for item in candidates if verify_pin(payload.pin, item.activation_pin_hash)]
        if len(matches) == 1:
            student = matches[0]

    if student is None:
        db.execute(text("""
            INSERT INTO public.audit_logs (action, entity_type, entity_id, details, created_at)
            VALUES ('student.activation.failed', 'student_email_hash', :email_hash, '{}'::jsonb, now())
        """), {"email_hash": email_hash})
        db.commit()
        raise HTTPException(status_code=403, detail="Activation PIN is invalid, expired, or not assigned to this student")

    existing_profile = db.execute(text("""
        SELECT local_user_id, role, school_id, is_active
        FROM public.profiles
        WHERE id = CAST(:auth_id AS uuid)
    """), {"auth_id": auth_id}).mappings().first()
    if existing_profile and (
        existing_profile["local_user_id"] != local_user.id
        or existing_profile["role"] != "student"
        or existing_profile["school_id"] != student.school_id
        or not existing_profile["is_active"]
    ):
        raise HTTPException(status_code=409, detail="This Supabase identity is already linked to another account")
    other_profile = db.execute(text("""
        SELECT id FROM public.profiles WHERE local_user_id = :local_user_id AND id <> CAST(:auth_id AS uuid) LIMIT 1
    """), {"local_user_id": local_user.id, "auth_id": auth_id}).first()
    if other_profile is not None:
        raise HTTPException(status_code=409, detail="This student account is already linked to another Supabase identity")
    if not existing_profile:
        db.execute(text("""
            INSERT INTO public.profiles
                (id, local_user_id, role, school_id, is_active, created_at, updated_at)
            VALUES
                (CAST(:auth_id AS uuid), :local_user_id, 'student', :school_id, true, now(), now())
        """), {"auth_id": auth_id, "local_user_id": local_user.id, "school_id": student.school_id})

    db.execute(text("""
        UPDATE public.students
        SET activated_at = now(), activation_pin_hash = NULL, activation_expires_at = NULL
        WHERE id = :student_id AND school_id = :school_id
    """), {"student_id": student.id, "school_id": student.school_id})
    db.execute(text("""
        INSERT INTO public.audit_logs (school_id, actor_user_id, action, entity_type, entity_id, details, created_at)
        VALUES (:school_id, :user_id, 'student.activation.succeeded', 'student', :student_id, '{}'::jsonb, now())
    """), {"school_id": student.school_id, "user_id": local_user.id, "student_id": str(student.id)})
    db.commit()
    return {"message": "Student account activated successfully."}


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
