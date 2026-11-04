from uuid import uuid4

import pytest
from sqlalchemy import text as sql_text

from app.config import settings
from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.user import User


def _owner(user):
    return SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=user.id,
        school_id=None,
        role="vortex_admin",
        is_admin=True,
    )


def _install_sqlite_profiles(db_session, monkeypatch):
    db_session.execute(sql_text("""
        CREATE TABLE profiles (
            id TEXT PRIMARY KEY,
            local_user_id INTEGER UNIQUE NOT NULL,
            role TEXT NOT NULL,
            school_id INTEGER,
            is_active BOOLEAN NOT NULL,
            created_at TEXT,
            updated_at TEXT
        )
    """))
    import app.routers.platform_staff as staff_router
    original_text = staff_router.text

    def sqlite_text(query):
        query = query.replace("public.profiles", "profiles")
        query = query.replace("CAST(:auth_id AS uuid)", ":auth_id")
        query = query.replace("now()", "CURRENT_TIMESTAMP")
        return original_text(query)

    monkeypatch.setattr(staff_router, "text", sqlite_text)


def test_owner_can_invite_support_staff_and_link_both_identity_records(
    client, seed_two_schools, db_session, monkeypatch
):
    _install_sqlite_profiles(db_session, monkeypatch)
    monkeypatch.setattr(settings, "supabase_secret_key", "server-only-test-secret")
    import app.routers.platform_staff as staff_router
    monkeypatch.setattr(staff_router, "_staff_roles_schema_ready", lambda db: True)
    auth_id = str(uuid4())
    invited = []
    monkeypatch.setattr(staff_router, "invite_auth_user", lambda email, name: invited.append((email, name)) or auth_id)

    owner = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _owner(owner)
    response = client.post("/platform/staff/invitations", json={
        "email": "  support@example.com ",
        "full_name": "  Support Officer  ",
        "role": "vortex_support",
    })

    assert response.status_code == 201
    assert response.json()["role"] == "vortex_support"
    assert invited == [("support@example.com", "Support Officer")]
    local = db_session.query(User).filter_by(email="support@example.com").one()
    assert local.role == "vortex_support"
    assert local.school_id is None
    assert local.is_admin is False
    profile = db_session.execute(sql_text("SELECT * FROM profiles WHERE id = :id"), {"id": auth_id}).mappings().one()
    assert profile["local_user_id"] == local.id
    assert profile["role"] == "vortex_support"
    assert profile["school_id"] is None


def test_school_admin_cannot_invite_platform_staff(client, seed_two_schools):
    owner = seed_two_schools["u1"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=owner.id, school_id=owner.school_id,
        role="owner", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.post("/platform/staff/invitations", json={
        "email": "support@example.com", "full_name": "Support Officer", "role": "vortex_support"
    })

    assert response.status_code == 403


def test_platform_support_cannot_invite_staff(client, seed_two_schools):
    owner = seed_two_schools["admin"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=owner.id, school_id=None,
        role="vortex_support", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.post("/platform/staff/invitations", json={
        "email": "support@example.com", "full_name": "Support Officer", "role": "vortex_support"
    })

    assert response.status_code == 403


def test_invitation_cannot_create_another_platform_admin(client, seed_two_schools):
    owner = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _owner(owner)

    response = client.post("/platform/staff/invitations", json={
        "email": "second-admin@example.com", "full_name": "Second Admin", "role": "vortex_admin"
    })

    assert response.status_code == 422


def test_invitation_requires_server_secret(client, seed_two_schools, monkeypatch):
    monkeypatch.setattr(settings, "supabase_secret_key", "")
    owner = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _owner(owner)

    response = client.post("/platform/staff/invitations", json={
        "email": "support@example.com", "full_name": "Support Officer", "role": "vortex_support"
    })

    assert response.status_code == 503


def test_duplicate_local_email_is_rejected_before_auth_invite(client, seed_two_schools, monkeypatch):
    monkeypatch.setattr(settings, "supabase_secret_key", "server-only-test-secret")
    owner = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _owner(owner)

    response = client.post("/platform/staff/invitations", json={
        "email": owner.email, "full_name": "Duplicate", "role": "vortex_support"
    })

    assert response.status_code == 409


def test_failed_profile_link_triggers_auth_user_compensation(
    client, seed_two_schools, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "supabase_secret_key", "server-only-test-secret")
    import app.routers.platform_staff as staff_router
    monkeypatch.setattr(staff_router, "_staff_roles_schema_ready", lambda db: True)
    auth_id = str(uuid4())
    deleted = []
    monkeypatch.setattr(staff_router, "invite_auth_user", lambda email, name: auth_id)
    monkeypatch.setattr(staff_router, "delete_auth_user", lambda user_id: deleted.append(user_id))
    owner = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _owner(owner)

    response = client.post("/platform/staff/invitations", json={
        "email": "rollback@example.com", "full_name": "Rollback User", "role": "vortex_auditor"
    })

    assert response.status_code == 503
    assert deleted == [auth_id]
    assert db_session.query(User).filter_by(email="rollback@example.com").first() is None


def test_invitation_is_blocked_until_staff_role_migration_is_applied(client, seed_two_schools, monkeypatch):
    monkeypatch.setattr(settings, "supabase_secret_key", "server-only-test-secret")
    import app.routers.platform_staff as staff_router
    monkeypatch.setattr(staff_router, "_staff_roles_schema_ready", lambda db: False)
    monkeypatch.setattr(staff_router, "invite_auth_user", lambda email, name: pytest.fail("must not call Supabase before migration"))
    owner = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _owner(owner)

    response = client.post("/platform/staff/invitations", json={
        "email": "migration@example.com", "full_name": "Migration Test", "role": "vortex_support"
    })

    assert response.status_code == 503
    assert "migration" in response.json()["detail"].lower()
