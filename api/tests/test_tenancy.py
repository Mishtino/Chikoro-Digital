from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app


def _principal(user, school_id, role="owner", is_admin=False):
    return SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=user.id,
        school_id=school_id,
        role=role,
        is_admin=is_admin,
    )


def test_tenancy_isolation(client, seed_two_schools):
    data = seed_two_schools
    owner_one = _principal(data["u1"], data["s1"].id)
    owner_two = _principal(data["u2"], data["s2"].id)
    platform_admin = _principal(data["admin"], None, role="admin", is_admin=True)

    app.dependency_overrides[get_supabase_principal] = lambda: owner_one

    response = client.get(f"/schools/{data['s1'].id}")
    assert response.status_code == 200

    response = client.get(f"/schools/{data['s2'].id}")
    assert response.status_code == 403

    response = client.get("/users")
    assert response.status_code == 200
    emails = [user["email"] for user in response.json()]
    assert "owner1@test.com" in emails
    assert "owner2@test.com" not in emails

    app.dependency_overrides[get_supabase_principal] = lambda: owner_two
    response = client.get(f"/schools/{data['s2'].id}")
    assert response.status_code == 200

    app.dependency_overrides[get_supabase_principal] = lambda: platform_admin
    response = client.get(f"/schools/{data['s2'].id}")
    assert response.status_code == 200
    response = client.get("/schools")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_legacy_local_login_is_retired(client):
    response = client.post("/auth/login", data={"username": "old@example.com", "password": "password"})
    assert response.status_code == 410
