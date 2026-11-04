from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app


def _platform_principal(user):
    return SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=user.id,
        school_id=None,
        role="vortex_admin",
        is_admin=True,
    )


def test_platform_audit_logs_are_paginated_and_include_actor(client, seed_two_schools, db_session):
    from app.models.audit import AuditLog

    admin = seed_two_schools["admin"]
    school = seed_two_schools["s1"]
    db_session.add(AuditLog(
        school_id=None,
        actor_user_id=admin.id,
        action="school.status_change",
        entity_type="school",
        entity_id=str(school.id),
        details={"previous_status": "onboarding", "new_status": "live"},
    ))
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _platform_principal(admin)

    response = client.get("/platform/audit-logs?limit=10&offset=0")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    record = next(item for item in body["items"] if item["action"] == "school.status_change")
    assert record["actor_email"] == admin.email
    assert record["details"]["new_status"] == "live"


def test_school_admin_cannot_read_platform_audit_logs(client, seed_two_schools):
    owner = seed_two_schools["u1"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=owner.id,
        school_id=owner.school_id,
        role="owner",
        is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.get("/platform/audit-logs")

    assert response.status_code == 403
