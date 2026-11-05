from uuid import uuid4

import pytest
from sqlalchemy import text as sql_text

from app.config import settings
from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.school import School
from app.models.user import User


def _school_admin(user, role="owner"):
    return SupabasePrincipal(
        auth_user_id=uuid4(), user_id=user.id, school_id=user.school_id,
        role=role, is_admin=False,
    )


def _install_profiles(db_session, monkeypatch):
    db_session.execute(sql_text("DROP TABLE IF EXISTS profiles"))
    db_session.execute(sql_text("""
        CREATE TABLE profiles (
            id TEXT PRIMARY KEY, local_user_id INTEGER UNIQUE,
            role TEXT NOT NULL, school_id INTEGER, is_active BOOLEAN NOT NULL,
            created_at TEXT, updated_at TEXT
        )
    """))
    db_session.execute(sql_text("DELETE FROM profiles"))
    import app.routers.school_staff as router
    monkeypatch.setattr(router, "school_staff_role_schema_ready", lambda db: True)
    monkeypatch.setattr(router, "link_pending_staff_profile", lambda db, auth_id, local_id, role, school_id:
        db.execute(sql_text("""
            UPDATE profiles SET local_user_id=:local_id, role=:role, school_id=:school_id, is_active=0
            WHERE id=:auth_id AND local_user_id IS NULL AND role='pending' AND is_active=0
        """), {"auth_id": auth_id, "local_id": local_id, "role": role, "school_id": school_id})
    )


def _configure(monkeypatch):
    monkeypatch.setattr(settings, "school_staff_invitations_enabled", True)
    monkeypatch.setattr(settings, "supabase_secret_key", "server-only-test-secret")


def test_owner_invitation_creates_inactive_school_scoped_account(
    client, seed_two_schools, db_session, monkeypatch
):
    _install_profiles(db_session, monkeypatch)
    _configure(monkeypatch)
    import app.routers.school_staff as router
    auth_id = str(uuid4())
    def fake_invite(email, name):
        db_session.execute(sql_text("""
            INSERT INTO profiles (id, role, school_id, is_active) VALUES (:id, 'pending', NULL, 0)
        """), {"id": auth_id})
        return auth_id
    monkeypatch.setattr(router, "invite_auth_user", fake_invite)
    owner = seed_two_schools["u1"]
    school = db_session.get(School, owner.school_id)
    school.status = "live"
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _school_admin(owner)

    response = client.post("/users/invitations", json={
        "email": "  new.teacher@example.com ", "full_name": "  New Teacher  ", "role": "teacher"
    })

    assert response.status_code == 201, response.text
    assert response.json()["activation_pending"] is True
    local = db_session.query(User).filter_by(email="new.teacher@example.com").one()
    assert local.role == "teacher" and local.school_id == owner.school_id
    assert local.is_active is False and local.is_admin is False
    profile = db_session.execute(sql_text("SELECT * FROM profiles WHERE id=:id"), {"id": auth_id}).mappings().one()
    assert profile["local_user_id"] == local.id
    assert profile["role"] == "teacher" and profile["school_id"] == owner.school_id
    assert profile["is_active"] == 0


def test_headmaster_cannot_invite_another_headmaster(client, seed_two_schools):
    headmaster = seed_two_schools["u1"]
    app.dependency_overrides[get_supabase_principal] = lambda: _school_admin(headmaster, "headmaster")
    response = client.post("/users/invitations", json={
        "email": "another@example.com", "full_name": "Another Head", "role": "headmaster"
    })
    assert response.status_code == 403


def test_school_invitation_is_disabled_by_default(client, seed_two_schools, monkeypatch):
    monkeypatch.setattr(settings, "school_staff_invitations_enabled", False)
    owner = seed_two_schools["u1"]
    app.dependency_overrides[get_supabase_principal] = lambda: _school_admin(owner)
    response = client.post("/users/invitations", json={
        "email": "new@example.com", "full_name": "New Teacher", "role": "teacher"
    })
    assert response.status_code == 503


def test_school_invitation_requires_live_school(client, seed_two_schools, monkeypatch):
    _install_profiles(db_session=None, monkeypatch=monkeypatch) if False else None
    _configure(monkeypatch)
    import app.routers.school_staff as router
    monkeypatch.setattr(router, "school_staff_role_schema_ready", lambda db: True)
    owner = seed_two_schools["u1"]
    app.dependency_overrides[get_supabase_principal] = lambda: _school_admin(owner)
    monkeypatch.setattr(router, "invite_auth_user", lambda *args: pytest.fail("must not invite before school is live"))
    response = client.post("/users/invitations", json={
        "email": "new@example.com", "full_name": "New Teacher", "role": "teacher"
    })
    assert response.status_code == 409
