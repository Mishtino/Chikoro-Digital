import pytest
from fastapi import HTTPException
from uuid import uuid4

from app.deps_supabase import SupabasePrincipal
from app.services.school_staff_access import (
    authorize_school_staff_write,
    authorize_school_staff_role_change,
    ensure_not_self_deactivation,
)


def principal(role, school_id=12, is_admin=False, user_id=7):
    return SupabasePrincipal(
        auth_user_id=uuid4(), user_id=user_id, school_id=school_id,
        role=role, is_admin=is_admin,
    )


@pytest.mark.parametrize("role", ["owner", "headmaster"])
@pytest.mark.parametrize("target_role", ["bursar", "teacher"])
def test_school_lead_can_assign_permitted_staff_roles(role, target_role):
    actor = principal(role)
    assert authorize_school_staff_write(actor, 12, target_role) == 12


def test_owner_can_invite_headmaster():
    assert authorize_school_staff_write(principal("owner"), 12, "headmaster") == 12


@pytest.mark.parametrize("role,target_role", [
    ("headmaster", "headmaster"),
    ("headmaster", "owner"),
    ("owner", "owner"),
    ("owner", "parent"),
    ("owner", "student"),
    ("owner", "vortex_admin"),
])
def test_school_lead_cannot_assign_protected_roles(role, target_role):
    with pytest.raises(HTTPException) as error:
        authorize_school_staff_write(principal(role), 12, target_role)
    assert error.value.status_code == 403


def test_platform_admin_flag_does_not_grant_school_staff_write():
    with pytest.raises(HTTPException) as error:
        authorize_school_staff_write(principal("owner", is_admin=True), 12, "teacher")
    assert error.value.status_code == 403


@pytest.mark.parametrize("role", ["student", "parent", "teacher", "vortex_support", "vortex_auditor"])
def test_non_school_leads_cannot_invite_staff(role):
    with pytest.raises(HTTPException) as error:
        authorize_school_staff_write(principal(role), 12, "teacher")
    assert error.value.status_code == 403


def test_school_lead_cannot_write_to_another_school():
    with pytest.raises(HTTPException) as error:
        authorize_school_staff_write(principal("owner", school_id=12), 99, "teacher")
    assert error.value.status_code == 403


def test_headmaster_cannot_promote_staff_to_headmaster():
    with pytest.raises(HTTPException) as error:
        authorize_school_staff_role_change(principal("headmaster"), 12, "headmaster")
    assert error.value.status_code == 403


def test_owner_can_change_staff_to_headmaster():
    assert authorize_school_staff_role_change(principal("owner"), 12, "headmaster") == 12


def test_self_deactivation_is_rejected():
    with pytest.raises(HTTPException) as error:
        ensure_not_self_deactivation(7, 7)
    assert error.value.status_code == 409


def test_deactivating_another_user_is_allowed_by_self_check():
    assert ensure_not_self_deactivation(7, 8) is None
