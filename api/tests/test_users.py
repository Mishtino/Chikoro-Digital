from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.user import User
from app.services.auth import hash_password


def _principal(user, role=None, school_id=None, is_admin=False):
    return SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=user.id,
        school_id=user.school_id if school_id is None else school_id,
        role=role or user.role,
        is_admin=is_admin,
    )


def test_school_owner_sees_only_staff_in_own_school(client, seed_two_schools, db_session):
    data = seed_two_schools
    teacher = User(
        email="teacher1@test.com",
        full_name="Teacher One",
        password_hash=hash_password("unused"),
        role="teacher",
        school_id=data["s1"].id,
    )
    student = User(
        email="student1@test.com",
        full_name="Student One",
        password_hash=hash_password("unused"),
        role="student",
        school_id=data["s1"].id,
    )
    other_school_teacher = User(
        email="teacher2@test.com",
        full_name="Teacher Two",
        password_hash=hash_password("unused"),
        role="teacher",
        school_id=data["s2"].id,
    )
    db_session.add_all([teacher, student, other_school_teacher])
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(data["u1"])

    response = client.get("/users")

    assert response.status_code == 200
    assert [row["email"] for row in response.json()] == ["owner1@test.com", "teacher1@test.com"]


def test_school_headmaster_cannot_request_another_school_staff(client, seed_two_schools):
    owner = seed_two_schools["u1"]
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(owner, role="headmaster")

    response = client.get(f"/users?school_id={seed_two_schools['s2'].id}")

    assert response.status_code == 403


def test_vortex_admin_must_select_one_school_for_staff_directory(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(
        admin, role="vortex_admin", school_id=None, is_admin=True
    )

    response = client.get("/users")

    assert response.status_code == 400


def test_vortex_admin_can_view_one_school_staff_only(client, seed_two_schools, db_session):
    data = seed_two_schools
    teacher = User(
        email="teacher1@test.com",
        full_name="Teacher One",
        password_hash=hash_password("unused"),
        role="teacher",
        school_id=data["s1"].id,
    )
    parent = User(
        email="parent1@test.com",
        full_name="Parent One",
        password_hash=hash_password("unused"),
        role="parent",
        school_id=data["s1"].id,
    )
    db_session.add_all([teacher, parent])
    db_session.commit()
    admin = data["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(
        admin, role="vortex_admin", school_id=None, is_admin=True
    )

    response = client.get(f"/users?school_id={data['s1'].id}")

    assert response.status_code == 200
    assert [row["email"] for row in response.json()] == ["owner1@test.com", "teacher1@test.com"]


def test_platform_support_cannot_access_school_staff_directory(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(
        admin, role="vortex_support", school_id=None
    )

    response = client.get(f"/users?school_id={seed_two_schools['s1'].id}")

    assert response.status_code == 403


def test_school_owner_with_platform_admin_flag_is_not_treated_as_school_admin(client, seed_two_schools):
    owner = seed_two_schools["u1"]
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(
        owner, role="owner", school_id=owner.school_id, is_admin=True
    )

    response = client.get("/users")

    assert response.status_code == 403
