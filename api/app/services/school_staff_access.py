"""Authorization policy for school staff account lifecycle operations.

This module deliberately contains no Auth or database side effects. It is a
pure policy layer to be called by invitation/role/deactivation endpoints only
after the actor has been resolved from a verified Supabase profile.
"""
from fastapi import HTTPException

INVITABLE_ROLES = frozenset({"headmaster", "bursar", "teacher"})
ROLE_CHANGE_TARGETS = {
    "owner": frozenset({"headmaster", "bursar", "teacher"}),
    "headmaster": frozenset({"bursar", "teacher"}),
}


def authorize_school_staff_write(actor, target_school_id: int, target_role: str | None = None):
    """Authorize a school-scoped staff write and return the bound school ID."""
    if actor.is_admin or actor.role not in {"owner", "headmaster"}:
        raise HTTPException(status_code=403, detail="School staff administration permission required")
    if actor.school_id is None or actor.school_id != target_school_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if target_role is not None and target_role not in INVITABLE_ROLES:
        raise HTTPException(status_code=403, detail="This role cannot be assigned through school staff administration")
    if target_role is not None and target_role not in ROLE_CHANGE_TARGETS.get(actor.role, frozenset()):
        raise HTTPException(status_code=403, detail="Insufficient permission to assign this staff role")
    return actor.school_id


def authorize_school_staff_role_change(actor, target_school_id: int, new_role: str):
    """Apply the stricter role-change matrix; ownership transfer is separate."""
    if new_role not in ROLE_CHANGE_TARGETS.get(actor.role, frozenset()):
        raise HTTPException(status_code=403, detail="Insufficient permission to assign this staff role")
    return authorize_school_staff_write(actor, target_school_id, new_role)


def ensure_not_self_deactivation(actor_user_id: int, target_user_id: int):
    if actor_user_id == target_user_id:
        raise HTTPException(status_code=409, detail="Self-deactivation is not permitted")
