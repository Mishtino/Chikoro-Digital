from uuid import uuid4

import pytest
from sqlalchemy import text as sql_text

from app.config import settings
from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.audit import AuditLog
from app.models.school import School
from app.models.user import User


def _actor(user, role="owner"):
    return SupabasePrincipal(
        auth_user_id=uuid4(), user_id=user.id, school_id=user.school_id,
        role=role, is_admin=False,
    )


def _profiles(db_session, monkeypatch):
    db_session.execute(sql_text("DROP TABLE IF EXISTS profiles"))
    db_session.execute(sql_text("""
        CREATE TABLE profiles (
            id TEXT PRIMARY KEY, local_user_id INTEGER UNIQUE,
            role TEXT NOT NULL, school_id INTEGER, is_active BOOLEAN NOT NULL,
            created_at TEXT, updated_at TEXT
        )
    """))
    import app.routers.school_staff as router
    monkeypatch.setattr(router, "school_staff_role_schema_ready", lambda db: True)
    monkeypatch.setattr(router, "text", lambda query: sql_text(
        query.replace("public.profiles", "profiles").replace("CAST(:auth_id AS uuid)", ":auth_id")
        .replace("now()", "CURRENT_TIMESTAMP").replace("FOR UPDATE", "")
    ))


def _add_staff(db_session, school_id, role="teacher", active=True):
    staff = User(
        email=f"{uuid4().hex}@example.com", full_name="School Staff",
        password_hash="not-a-login-password", role=role, school_id=school_id,
        is_active=active, is_admin=False,
    )
    db_session.add(staff)
    db_session.flush()
    auth_id = str(uuid4())
    db_session.execute(sql_text("""
        INSERT INTO profiles (id, local_user_id, role, school_id, is_active)
        VALUES (:id, :local_id, :role, :school_id, :active)
    """), {"id": auth_id, "local_id": staff.id, "role": role, "school_id": school_id, "active": active})
    db_session.commit()
    return staff, auth_id


def _enable(monkeypatch):
    monkeypatch.setattr(settings, "school_staff_lifecycle_enabled", True)


def test_owner_can_change_staff_role_and_both_records_stay_in_sync(
    client, seed_two_schools, db_session, monkeypatch
):
    _profiles(db_session, monkeypatch)
    _enable(monkeypatch)
    owner = seed_two_schools["u1"]
    staff, auth_id = _add_staff(db_session, owner.school_id)
    school = db_session.get(School, owner.school_id)
    school.status = "live"
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _actor(owner)
    response = client.patch(f"/users/{staff.id}/role", json={"role": "bursar"})
    assert response.status_code == 200, response.text
    db_session.refresh(staff)
    profile = db_session.execute(sql_text("SELECT role FROM profiles WHERE id=:id"), {"id": auth_id}).scalar_one()
    assert staff.role == profile == "bursar"
    assert db_session.query(AuditLog).filter_by(action="school.staff.role_changed").count() == 1


def test_headmaster_cannot_promote_staff_to_headmaster(client, seed_two_schools, db_session, monkeypatch):
    _profiles(db_session, monkeypatch)
    _enable(monkeypatch)
    headmaster = seed_two_schools["u1"]
    staff, _ = _add_staff(db_session, headmaster.school_id)
    app.dependency_overrides[get_supabase_principal] = lambda: _actor(headmaster, "headmaster")
    response = client.patch(f"/users/{staff.id}/role", json={"role": "headmaster"})
    assert response.status_code == 403


def test_owner_can_deactivate_staff_and_api_profile_is_disabled(
    client, seed_two_schools, db_session, monkeypatch
):
    _profiles(db_session, monkeypatch)
    _enable(monkeypatch)
    owner = seed_two_schools["u1"]
    staff, auth_id = _add_staff(db_session, owner.school_id)
    app.dependency_overrides[get_supabase_principal] = lambda: _actor(owner)
    response = client.patch(f"/users/{staff.id}/status", json={"is_active": False})
    assert response.status_code == 200, response.text
    db_session.refresh(staff)
    active = db_session.execute(sql_text("SELECT is_active FROM profiles WHERE id=:id"), {"id": auth_id}).scalar_one()
    assert staff.is_active is False and active == 0
    assert db_session.query(AuditLog).filter_by(action="school.staff.deactivated").count() == 1


def test_headmaster_cannot_deactivate_headmaster_or_owner(
    client, seed_two_schools, db_session, monkeypatch
):
    _profiles(db_session, monkeypatch)
    _enable(monkeypatch)
    headmaster = seed_two_schools["u1"]
    staff, _ = _add_staff(db_session, headmaster.school_id, role="headmaster")
    app.dependency_overrides[get_supabase_principal] = lambda: _actor(headmaster, "headmaster")
    response = client.patch(f"/users/{staff.id}/status", json={"is_active": False})
    assert response.status_code == 403


def test_staff_lifecycle_is_disabled_by_default(client, seed_two_schools, db_session, monkeypatch):
    _profiles(db_session, monkeypatch)
    monkeypatch.setattr(settings, "school_staff_lifecycle_enabled", False)
    owner = seed_two_schools["u1"]
    staff, _ = _add_staff(db_session, owner.school_id)
    app.dependency_overrides[get_supabase_principal] = lambda: _actor(owner)
    response = client.patch(f"/users/{staff.id}/status", json={"is_active": False})
    assert response.status_code == 503
