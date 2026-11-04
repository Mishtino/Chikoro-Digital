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
