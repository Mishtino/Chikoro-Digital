from types import SimpleNamespace
from uuid import uuid4

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


class FakeSession:
    def __init__(self, row):
        self.row = row
        self.statement = None
        self.params = None

    def execute(self, statement, params):
        self.statement = str(statement)
        self.params = params
        return FakeResult(self.row)


def test_resolve_profile_returns_only_trusted_database_identity():
    row = {
        "id": uuid4(),
        "local_user_id": 27,
        "role": "student",
        "school_id": 4,
        "is_active": True,
        "is_admin": False,
        "local_user_is_active": True,
    }
    db = FakeSession(row)

    profile = resolve_profile(db, {"sub": str(row["id"]), "user_metadata": {"role": "admin"}})

    assert profile["role"] == "student"
    assert profile["local_user_id"] == 27
    assert profile["school_id"] == 4
    assert "user_metadata" not in db.statement
    assert db.params["auth_id"] == str(row["id"])


@pytest.mark.parametrize(
    "row",
    [
        None,
        {"id": uuid4(), "local_user_id": 1, "role": "admin", "school_id": None,
         "is_active": False, "is_admin": True, "local_user_is_active": True},
        {"id": uuid4(), "local_user_id": 1, "role": "admin", "school_id": None,
         "is_active": True, "is_admin": True, "local_user_is_active": False},
        {"id": uuid4(), "local_user_id": None, "role": "pending", "school_id": None,
         "is_active": False, "is_admin": False, "local_user_is_active": None},
    ],
)
def test_resolve_profile_rejects_unlinked_or_inactive_accounts(row):
    with pytest.raises(HTTPException) as exc:
        resolve_profile(FakeSession(row), {"sub": str(uuid4())})

    assert exc.value.status_code == 403
