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
        CREATE TABLE IF NOT EXISTS profiles (
            id TEXT PRIMARY KEY,
            local_user_id INTEGER UNIQUE NOT NULL,
            role TEXT NOT NULL,
            school_id INTEGER,
            is_active BOOLEAN NOT NULL,
            created_at TEXT,
            updated_at TEXT
        )
    """))
    db_session.execute(sql_text("DELETE FROM profiles"))
    import app.routers.platform_staff as staff_router
    monkeypatch.setattr(staff_router, "_staff_roles_schema_ready", lambda db: True)
    original_text = staff_router.text

    def sqlite_text(query):
        query = query.replace("public.profiles", "profiles")
        query = query.replace("public.users", "users")
        query = query.replace("CAST(:auth_id AS uuid)", ":auth_id")
        query = query.replace("now()", "CURRENT_TIMESTAMP")
        query = query.replace("FOR UPDATE", "")
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
    import app.routers.platform_staff as staff_router
    monkeypatch.setattr(staff_router, "_staff_roles_schema_ready", lambda db: True)
    monkeypatch.setattr(settings, "supabase_secret_key", "")
    owner = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _owner(owner)

    response = client.post("/platform/staff/invitations", json={
        "email": "support@example.com", "full_name": "Support Officer", "role": "vortex_support"
    })

    assert response.status_code == 503


def test_duplicate_local_email_is_rejected_before_auth_invite(client, seed_two_schools, monkeypatch):
    import app.routers.platform_staff as staff_router
    monkeypatch.setattr(staff_router, "_staff_roles_schema_ready", lambda db: True)
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



def _create_managed_staff(db_session, role="vortex_support", active=True):
    local = User(
        email=f"{role}-{uuid4().hex[:8]}@example.com",
        full_name="Platform Staff",
        password_hash="not-a-login-password",
        role=role,
        school_id=None,
        is_active=active,
        is_admin=False,
    )
    db_session.add(local)
    db_session.flush()
    auth_id = str(uuid4())
    db_session.execute(sql_text("""
        INSERT INTO profiles (id, local_user_id, role, school_id, is_active, created_at, updated_at)
        VALUES (:id, :local_id, :role, NULL, :active, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """), {"id": auth_id, "local_id": local.id, "role": role, "active": active})
    db_session.commit()
    return auth_id, local



def test_platform_staff_listing_excludes_mismatched_or_tenant_linked_identities(
    client, seed_two_schools, db_session, monkeypatch
):
    _install_sqlite_profiles(db_session, monkeypatch)
    valid_auth_id, valid_user = _create_managed_staff(db_session, role="vortex_support")
    tenant_user = seed_two_schools["u1"]
    tenant_auth_id = str(uuid4())
    mismatched_user = User(
        email=f"mismatch-{uuid4().hex[:8]}@example.com",
        full_name="Mismatched Role",
        password_hash="not-a-login-password",
        role="teacher",
        school_id=None,
        is_active=True,
        is_admin=False,
    )
    admin_flag_user = User(
        email=f"admin-flag-{uuid4().hex[:8]}@example.com",
        full_name="Unexpected Admin Flag",
        password_hash="not-a-login-password",
        role="vortex_support",
        school_id=None,
        is_active=True,
        is_admin=True,
    )
    db_session.add_all([mismatched_user, admin_flag_user])
    db_session.flush()
    db_session.execute(sql_text("""
        INSERT INTO profiles (id, local_user_id, role, school_id, is_active, created_at, updated_at)
        VALUES
          (:tenant_auth, :tenant_id, 'vortex_support', NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
          (:mismatch_auth, :mismatch_id, 'vortex_support', NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
          (:admin_auth, :admin_id, 'vortex_support', NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """), {
        "tenant_auth": tenant_auth_id,
        "tenant_id": tenant_user.id,
        "mismatch_auth": str(uuid4()),
        "mismatch_id": mismatched_user.id,
        "admin_auth": str(uuid4()),
        "admin_id": admin_flag_user.id,
    })
    db_session.commit()

    owner = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _owner(owner)
    response = client.get("/platform/staff")

    assert response.status_code == 200
    listed_ids = {row["auth_user_id"] for row in response.json()}
    assert listed_ids == {valid_auth_id}

def test_owner_can_disable_and_reenable_platform_staff(client, seed_two_schools, db_session, monkeypatch):
    _install_sqlite_profiles(db_session, monkeypatch)
    auth_id, local = _create_managed_staff(db_session)
    owner = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _owner(owner)

    disabled = client.patch(f"/platform/staff/{auth_id}/status", json={"is_active": False})
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False
    db_session.refresh(local)
    profile = db_session.execute(sql_text("SELECT is_active FROM profiles WHERE id = :id"), {"id": auth_id}).first()
    assert local.is_active is False
    assert profile[0] == 0

    enabled = client.patch(f"/platform/staff/{auth_id}/status", json={"is_active": True})
    assert enabled.status_code == 200
    db_session.refresh(local)
    profile = db_session.execute(sql_text("SELECT is_active FROM profiles WHERE id = :id"), {"id": auth_id}).first()
    assert local.is_active is True
    assert profile[0] == 1


def test_owner_account_cannot_be_disabled_through_staff_lifecycle(client, seed_two_schools, db_session, monkeypatch):
    _install_sqlite_profiles(db_session, monkeypatch)
    owner = seed_two_schools["admin"]
    owner_auth_id = str(uuid4())
    db_session.execute(sql_text("""
        INSERT INTO profiles (id, local_user_id, role, school_id, is_active, created_at, updated_at)
        VALUES (:id, :local_id, 'vortex_admin', NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """), {"id": owner_auth_id, "local_id": owner.id})
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _owner(owner)

    response = client.patch(f"/platform/staff/{owner_auth_id}/status", json={"is_active": False})
    assert response.status_code == 404
    db_session.refresh(owner)
    assert owner.is_active is True


def test_school_admin_cannot_change_platform_staff_status(client, seed_two_schools):
    school_owner = seed_two_schools["u1"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=school_owner.id, school_id=school_owner.school_id,
        role="owner", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.patch(f"/platform/staff/{uuid4()}/status", json={"is_active": False})
    assert response.status_code == 403
