from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app


def _principal(user, role, is_admin=False, school_id=None):
    return SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=user.id,
        school_id=school_id,
        role=role,
        is_admin=is_admin,
    )


def test_platform_support_can_read_school_directory_but_not_write(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(admin, "vortex_support")

    listing = client.get("/schools")
    create = client.post("/schools", json={"code": "NEW001", "name": "New School"})
    status_change = client.patch(f"/schools/{seed_two_schools['s1'].id}/status", json={"status": "suspended"})

    assert listing.status_code == 200
    assert len(listing.json()) == 2
    assert create.status_code == 403
    assert status_change.status_code == 403


def test_platform_auditor_can_read_audit_but_not_school_directory(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(admin, "vortex_auditor")

    audit = client.get("/platform/audit-logs")
    schools = client.get("/schools")

    assert audit.status_code == 200
    assert schools.status_code == 403


def test_platform_support_cannot_read_audit_logs(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(admin, "vortex_support")

    response = client.get("/platform/audit-logs")

    assert response.status_code == 403


def test_platform_access_endpoint_returns_server_permissions(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(admin, "vortex_support")

    response = client.get("/platform/access/me")

    assert response.status_code == 200
    assert response.json()["is_platform_staff"] is True
    assert response.json()["is_platform_admin"] is False
    assert response.json()["permissions"] == ["platform:access:read", "schools:read"]
    assert "platform:staff:write" not in response.json()["permissions"]


def test_school_user_is_not_platform_staff(client, seed_two_schools):
    owner = seed_two_schools["u1"]
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(
        owner, "owner", school_id=owner.school_id
    )

    response = client.get("/platform/access/me")

    assert response.status_code == 200
    assert response.json()["is_platform_staff"] is False
    assert response.json()["permissions"] == []


def test_platform_auditor_cannot_read_individual_school_record(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(admin, "vortex_auditor")

    response = client.get(f"/schools/{seed_two_schools['s1'].id}")

    assert response.status_code == 403


def test_platform_support_can_read_individual_school_record(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(admin, "vortex_support")

    response = client.get(f"/schools/{seed_two_schools['s1'].id}")

    assert response.status_code == 200


def test_vortex_admin_has_platform_staff_write_permission(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(
        admin, "vortex_admin", is_admin=True
    )

    response = client.get("/platform/access/me")

    assert response.status_code == 200
    assert "platform:staff:write" in response.json()["permissions"]


def test_billing_role_is_not_yet_invitable(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(
        admin, "vortex_admin", is_admin=True
    )

    response = client.post("/platform/staff/invitations", json={
        "email": "billing@example.com",
        "full_name": "Billing Officer",
        "role": "vortex_billing",
    })

    assert response.status_code == 422
