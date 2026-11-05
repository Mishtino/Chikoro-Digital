from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.supabase_auth import resolve_profile


class FakeResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class FakeDB:
    def __init__(self, row):
        self.row = row
        self.statement = None
        self.params = None

    def execute(self, statement, params):
        self.statement = str(statement)
        self.params = params
        return FakeResult(self.row)


def profile_row(**overrides):
    row = {
        "id": "00000000-0000-0000-0000-000000000001",
        "local_user_id": 41,
        "role": "teacher",
        "school_id": 7,
        "is_active": True,
        "local_user_role": "teacher",
        "local_school_id": 7,
        "is_admin": False,
        "local_user_is_active": True,
    }
    row.update(overrides)
    return row


def test_resolves_active_school_scoped_profile_from_trusted_database_record():
    db = FakeDB(profile_row())
    result = resolve_profile(db, {"sub": "00000000-0000-0000-0000-000000000001"})

    assert result["local_user_id"] == 41
    assert result["school_id"] == 7
    assert result["role"] == "teacher"
    assert "user_metadata" not in db.statement
    assert db.params["auth_id"] == "00000000-0000-0000-0000-000000000001"


@pytest.mark.parametrize(
    "row",
    [
        None,
        profile_row(is_active=False),
        profile_row(local_user_id=None),
        profile_row(local_user_is_active=False),
    ],
)
def test_rejects_missing_or_inactive_profile_and_local_user(row):
    with pytest.raises(HTTPException) as exc:
        resolve_profile(FakeDB(row), {"sub": "00000000-0000-0000-0000-000000000001"})
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "overrides",
    [
        {"role": "headmaster"},
        {"school_id": 8},
        {"is_admin": True, "role": "vortex_admin", "local_user_role": "admin"},
        {"role": "vortex_admin", "local_user_role": "admin", "is_admin": False},
    ],
)
def test_rejects_role_or_tenant_mismatch(overrides):
    with pytest.raises(HTTPException) as exc:
        resolve_profile(FakeDB(profile_row(**overrides)), {"sub": "00000000-0000-0000-0000-000000000001"})
    assert exc.value.status_code == 403


def test_accepts_only_explicit_tenant_free_vortex_admin_bridge():
    row = profile_row(
        role="vortex_admin",
        local_user_role="admin",
        school_id=None,
        local_school_id=None,
        is_admin=True,
    )
    result = resolve_profile(FakeDB(row), {"sub": "00000000-0000-0000-0000-000000000001"})
    assert result["role"] == "vortex_admin"
    assert result["school_id"] is None
