from fastapi import HTTPException

from app.config import settings
from app.routers.auth import bootstrap_first_admin


class FakeResult:
    def __init__(self, *, scalar=None, rows=None, rowcount=None):
        self._scalar = scalar
        self._rows = rows or []
        self.rowcount = rowcount

    def scalar_one(self):
        return self._scalar

    def mappings(self):
        return self

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, *, owner_count=0, admins=None, auth_users=None, insert_rowcount=1):
        self.owner_count = owner_count
        self.admins = admins or []
        self.auth_users = auth_users or []
        self.insert_rowcount = insert_rowcount
        self.statements = []
        self.params = []
        self.committed = False
        self.rolled_back = False

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params or {})
        if "LOCK TABLE public.profiles" in sql:
            return FakeResult()
        if "count(*) FROM public.profiles" in sql:
            return FakeResult(scalar=self.owner_count)
        if "FROM public.users" in sql:
            return FakeResult(rows=self.admins)
        if "FROM auth.users" in sql:
            return FakeResult(rows=self.auth_users)
        if "INSERT INTO public.profiles" in sql:
            return FakeResult(rowcount=self.insert_rowcount)
        raise AssertionError(f"Unexpected SQL in bootstrap test: {sql}")

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _admin():
    return {
        "id": 91,
        "email": "operator@example.test",
        "role": "admin",
        "school_id": None,
        "is_active": True,
        "is_admin": True,
    }


def test_bootstrap_admin_links_only_one_confirmed_matching_auth_identity(monkeypatch):
    monkeypatch.setattr(settings, "admin_bootstrap_token", "x" * 48)
    monkeypatch.setattr(settings, "platform_owner_email", "operator@example.test")
    auth_id = "8f0a90a0-9d36-4c95-9e8d-78a9c934c4e2"
    db = FakeSession(
        admins=[_admin()],
        auth_users=[(auth_id,)],
    )

    result = bootstrap_first_admin(setup_token="x" * 48, db=db)

    assert result["message"].startswith("The verified platform administrator identity")
    assert db.committed is True
    assert db.rolled_back is False
    insert_index = next(
        i for i, sql in enumerate(db.statements)
        if "INSERT INTO public.profiles" in sql
    )
    assert db.params[insert_index] == {
        "auth_id": auth_id,
        "local_user_id": 91,
    }


def test_bootstrap_admin_rejects_invalid_token_before_database_access(monkeypatch):
    monkeypatch.setattr(settings, "admin_bootstrap_token", "x" * 48)
    db = FakeSession()

    try:
        bootstrap_first_admin(setup_token="wrong", db=db)
        assert False, "Expected invalid bootstrap token to be rejected"
    except HTTPException as exc:
        assert exc.status_code == 401

    assert db.statements == []


def test_bootstrap_admin_requires_exactly_one_active_unscoped_admin(monkeypatch):
    monkeypatch.setattr(settings, "admin_bootstrap_token", "x" * 48)
    monkeypatch.setattr(settings, "platform_owner_email", "operator@example.test")
    db = FakeSession(admins=[])

    try:
        bootstrap_first_admin(setup_token="x" * 48, db=db)
        assert False, "Expected missing platform owner to be rejected"
    except HTTPException as exc:
        assert exc.status_code == 409

    assert not any("INSERT INTO public.profiles" in sql for sql in db.statements)
    assert db.committed is False


def test_bootstrap_admin_requires_one_confirmed_auth_identity(monkeypatch):
    monkeypatch.setattr(settings, "admin_bootstrap_token", "x" * 48)
    monkeypatch.setattr(settings, "platform_owner_email", "operator@example.test")
    db = FakeSession(admins=[_admin()], auth_users=[])

    try:
        bootstrap_first_admin(setup_token="x" * 48, db=db)
        assert False, "Expected missing confirmed Auth identity to be rejected"
    except HTTPException as exc:
        assert exc.status_code == 409

    assert not any("INSERT INTO public.profiles" in sql for sql in db.statements)
    assert db.committed is False


def test_bootstrap_admin_refuses_existing_owner(monkeypatch):
    monkeypatch.setattr(settings, "admin_bootstrap_token", "x" * 48)
    db = FakeSession(owner_count=1)

    try:
        bootstrap_first_admin(setup_token="x" * 48, db=db)
        assert False, "Expected an already completed bootstrap to be rejected"
    except HTTPException as exc:
        assert exc.status_code == 409

    assert not any("INSERT INTO public.profiles" in sql for sql in db.statements)
