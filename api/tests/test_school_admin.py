from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app


def test_school_creation_normalizes_code_and_text(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=admin.id,
        school_id=None,
        role="vortex_admin",
        is_admin=True,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.post("/schools", json={
        "code": "  new-school  ",
        "name": "  New School  ",
        "province": "  Harare  ",
        "plan": "  pilot  ",
    })

    assert response.status_code == 201
    assert response.json()["code"] == "NEW-SCHOOL"
    assert response.json()["name"] == "New School"
    assert response.json()["province"] == "Harare"
    assert response.json()["plan"] == "pilot"


def test_school_creation_rejects_invalid_code(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=admin.id,
        school_id=None,
        role="vortex_admin",
        is_admin=True,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.post("/schools", json={
        "code": "bad code!",
        "name": "Invalid Code School",
    })

    assert response.status_code == 422


def test_school_creation_is_platform_admin_only(client, seed_two_schools):
    owner = seed_two_schools["u1"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=owner.id,
        school_id=owner.school_id,
        role="owner",
        is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.post("/schools", json={
        "code": "NEW-SCHOOL",
        "name": "New School",
    })

    assert response.status_code == 403


def test_school_creation_rejects_blank_name(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=admin.id,
        school_id=None,
        role="vortex_admin",
        is_admin=True,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.post("/schools", json={
        "code": "BLANK-NAME",
        "name": "   ",
    })

    assert response.status_code == 422


def test_legacy_admin_role_cannot_use_vortex_school_directory(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=admin.id,
        school_id=None,
        role="admin",
        is_admin=True,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.get("/schools")

    assert response.status_code == 403


def test_vortex_admin_can_suspend_school_and_audit_change(client, seed_two_schools, db_session):
    admin = seed_two_schools["admin"]
    school = seed_two_schools["s1"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=admin.id,
        school_id=None,
        role="vortex_admin",
        is_admin=True,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.patch(f"/schools/{school.id}/status", json={
        "status": "suspended",
        "reason": "Subscription review",
    })

    assert response.status_code == 200
    assert response.json()["status"] == "suspended"
    from app.models.audit import AuditLog
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "school.status_change",
        AuditLog.entity_id == str(school.id),
    ).order_by(AuditLog.id.desc()).first()
    assert audit is not None
    assert audit.details["previous_status"] == "onboarding"
    assert audit.details["new_status"] == "suspended"
    assert audit.details["reason"] == "Subscription review"


def test_school_admin_cannot_change_school_lifecycle_status(client, seed_two_schools):
    owner = seed_two_schools["u1"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=owner.id,
        school_id=owner.school_id,
        role="owner",
        is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.patch(f"/schools/{owner.school_id}/status", json={"status": "suspended"})

    assert response.status_code == 403


def test_school_lifecycle_rejects_unknown_status(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=admin.id,
        school_id=None,
        role="vortex_admin",
        is_admin=True,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.patch(f"/schools/{seed_two_schools['s1'].id}/status", json={"status": "deleted"})

    assert response.status_code == 422


def test_vortex_admin_can_update_school_profile_and_audit_changes(client, seed_two_schools, db_session):
    admin = seed_two_schools["admin"]
    school = seed_two_schools["s1"]
    old_name = school.name
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=admin.id,
        school_id=None,
        role="vortex_admin",
        is_admin=True,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.patch(f"/schools/{school.id}", json={
        "name": "  Updated Academy  ",
        "province": "  Bulawayo  ",
        "plan": "  standard  ",
    })

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Academy"
    assert response.json()["province"] == "Bulawayo"
    assert response.json()["plan"] == "standard"
    from app.models.audit import AuditLog
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "school.profile_update",
        AuditLog.entity_id == str(school.id),
    ).order_by(AuditLog.id.desc()).first()
    assert audit is not None
    assert audit.details["changes"]["name"] == {"from": old_name, "to": "Updated Academy"}
    assert audit.details["changes"]["province"]["to"] == "Bulawayo"


def test_school_profile_update_is_platform_admin_only(client, seed_two_schools):
    owner = seed_two_schools["u1"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=owner.id,
        school_id=owner.school_id,
        role="owner",
        is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.patch(f"/schools/{owner.school_id}", json={"name": "Not Allowed Academy"})

    assert response.status_code == 403


def test_platform_support_cannot_update_school_profile(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    school = seed_two_schools["s1"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=admin.id,
        school_id=None,
        role="vortex_support",
        is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.patch(f"/schools/{school.id}", json={"name": "Support Edited Academy"})

    assert response.status_code == 403


def test_school_profile_update_rejects_protected_or_unknown_fields(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    school = seed_two_schools["s1"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=admin.id,
        school_id=None,
        role="vortex_admin",
        is_admin=True,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.patch(f"/schools/{school.id}", json={"status": "live", "code": "CHANGED"})

    assert response.status_code == 422


def test_school_profile_update_rejects_empty_patch_and_blank_name(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    school = seed_two_schools["s1"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=admin.id,
        school_id=None,
        role="vortex_admin",
        is_admin=True,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    empty = client.patch(f"/schools/{school.id}", json={})
    blank = client.patch(f"/schools/{school.id}", json={"name": "   "})

    assert empty.status_code == 422
    assert blank.status_code == 422
