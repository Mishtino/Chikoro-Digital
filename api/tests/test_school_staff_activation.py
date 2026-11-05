from uuid import uuid4

from sqlalchemy import text as sql_text

from app.deps_supabase import get_supabase_principal
from app.main import app
from app.models.audit import AuditLog
from app.models.school import School
from app.models.user import User


def _install_activation_tables(db_session, monkeypatch):
    db_session.execute(sql_text("""
        CREATE TABLE IF NOT EXISTS profiles (
            id TEXT PRIMARY KEY, local_user_id INTEGER UNIQUE,
            role TEXT NOT NULL, school_id INTEGER, is_active BOOLEAN NOT NULL,
            created_at TEXT, updated_at TEXT
        )
    """))
    db_session.execute(sql_text("""
        CREATE TABLE IF NOT EXISTS auth_users (
            id TEXT PRIMARY KEY, email TEXT, email_confirmed_at TEXT
        )
    """))
    import app.routers.auth as auth_router
    original_text = auth_router.text
    monkeypatch.setattr(auth_router, "text", lambda query: sql_text(
        query.replace("auth.users", "auth_users").replace("public.profiles", "profiles")
        .replace("public.users", "users").replace("CAST(:auth_id AS uuid)", ":auth_id")
        .replace("now()", "CURRENT_TIMESTAMP").replace("FOR UPDATE OF p, u", "")
    ))


def test_staff_activation_requires_verified_invited_identity(
    client, seed_two_schools, db_session, monkeypatch
):
    _install_activation_tables(db_session, monkeypatch)
    import app.routers.auth as auth_router
    auth_id = str(uuid4())
    owner = seed_two_schools["u1"]
    school = db_session.get(School, owner.school_id)
    school.status = "live"
    staff = User(
        email="invitee@example.com", full_name="Invited Teacher",
        password_hash="random-not-a-password", role="teacher",
        school_id=school.id, is_active=False, is_admin=False,
    )
    db_session.add(staff)
    db_session.flush()
    db_session.execute(sql_text("""
        INSERT INTO profiles (id, local_user_id, role, school_id, is_active)
        VALUES (:id, :local_id, 'teacher', :school_id, 0)
    """), {"id": auth_id, "local_id": staff.id, "school_id": school.id})
    db_session.execute(sql_text("""
        INSERT INTO auth_users (id, email, email_confirmed_at)
        VALUES (:id, 'invitee@example.com', '2026-11-05T00:00:00')
    """), {"id": auth_id})
    db_session.commit()
    monkeypatch.setattr(auth_router, "verify_supabase_access_token", lambda token: {"sub": auth_id})
    response = client.post("/auth/staff/activate", headers={"Authorization": "Bearer verified-test-token"})
    assert response.status_code == 200, response.text
    db_session.refresh(staff)
    assert staff.is_active is True
    profile = db_session.execute(sql_text("SELECT is_active FROM profiles WHERE id=:id"), {"id": auth_id}).scalar_one()
    assert profile == 1
    assert db_session.query(AuditLog).filter_by(action="school.staff.activated").count() == 1


def test_staff_activation_rejects_unverified_email(
    client, seed_two_schools, db_session, monkeypatch
):
    _install_activation_tables(db_session, monkeypatch)
    import app.routers.auth as auth_router
    auth_id = str(uuid4())
    monkeypatch.setattr(auth_router, "verify_supabase_access_token", lambda token: {"sub": auth_id})
    db_session.execute(sql_text("""
        INSERT INTO auth_users (id, email, email_confirmed_at) VALUES (:id, 'invitee@example.com', NULL)
    """), {"id": auth_id})
    db_session.commit()
    response = client.post("/auth/staff/activate", headers={"Authorization": "Bearer verified-test-token"})
    assert response.status_code == 403


def test_staff_activation_cannot_be_used_for_unlinked_identity(
    client, seed_two_schools, db_session, monkeypatch
):
    _install_activation_tables(db_session, monkeypatch)
    import app.routers.auth as auth_router
    auth_id = str(uuid4())
    monkeypatch.setattr(auth_router, "verify_supabase_access_token", lambda token: {"sub": auth_id})
    db_session.execute(sql_text("""
        INSERT INTO auth_users (id, email, email_confirmed_at)
        VALUES (:id, 'unlinked@example.com', '2026-11-05T00:00:00')
    """), {"id": auth_id})
    db_session.commit()
    response = client.post("/auth/staff/activate", headers={"Authorization": "Bearer verified-test-token"})
    assert response.status_code == 403
