"""Database-side safeguards for school staff invitation linking.

Supabase Auth creates a pending profile via the auth.users trigger. This module
only binds that existing pending row to an inactive local staff record.
"""
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def school_staff_role_schema_ready(db: Session) -> bool:
    try:
        row = db.execute(text("""
            SELECT pg_get_constraintdef(c.oid), c.convalidated
            FROM pg_constraint AS c
            WHERE c.conrelid = 'public.profiles'::regclass
              AND c.conname = 'profiles_role_check'
        """)).first()
    except Exception:
        return False
    if not row or not row[1] or not row[0]:
        return False
    definition = str(row[0])
    return all(role in definition for role in (
        "pending", "owner", "headmaster", "bursar", "teacher"
    ))


def link_pending_staff_profile(
    db: Session, auth_user_id: str, local_user_id: int, role: str, school_id: int
) -> None:
    """Bind exactly one trigger-created pending profile; never overwrite a link."""
    normalized_id = str(UUID(str(auth_user_id)))
    row = db.execute(text("""
        SELECT local_user_id, role, school_id, is_active
        FROM public.profiles
        WHERE id = CAST(:auth_id AS uuid)
        FOR UPDATE
    """), {"auth_id": normalized_id}).mappings().first()
    if (
        row is None
        or row["local_user_id"] is not None
        or row["role"] != "pending"
        or row["school_id"] is not None
        or bool(row["is_active"])
    ):
        raise ValueError("Supabase identity is not an unused pending profile")

    result = db.execute(text("""
        UPDATE public.profiles
        SET local_user_id = :local_user_id,
            role = :role,
            school_id = :school_id,
            is_active = false,
            updated_at = now()
        WHERE id = CAST(:auth_id AS uuid)
          AND local_user_id IS NULL
          AND role = 'pending'
          AND school_id IS NULL
          AND is_active = false
    """), {
        "auth_id": normalized_id,
        "local_user_id": local_user_id,
        "role": role,
        "school_id": school_id,
    })
    if result.rowcount != 1:
        raise ValueError("Pending Supabase profile could not be linked")
