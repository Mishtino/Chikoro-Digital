from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app


def _set_principal(user, school_id, role="owner"):
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=user.id,
        school_id=school_id,
        role=role,
        is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal


def test_student_admissions_allocate_distinct_school_numbers(client, seed_two_schools):
    data = seed_two_schools
    _set_principal(data["u1"], data["s1"].id)

    first = client.post("/students", json={"first_name": "Ada", "last_name": "Moyo"})
    second = client.post("/students", json={"first_name": "Tariro", "last_name": "Ncube"})

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["student_number"] != second.json()["student_number"]
    assert first.json()["student_number"].startswith(data["s1"].code)
    assert second.json()["student_number"].startswith(data["s1"].code)


def test_student_lookup_cannot_cross_school_boundary(client, seed_two_schools):
    data = seed_two_schools
    _set_principal(data["u1"], data["s1"].id)

    created = client.post("/students", json={"first_name": "Tendai", "last_name": "Dube"})
    assert created.status_code == 201

    # A student identifier from another tenant must not be readable.
    other_school_student_id = created.json()["id"]
    _set_principal(data["u2"], data["s2"].id)
    response = client.get(f"/students/{other_school_student_id}")

    assert response.status_code == 403
