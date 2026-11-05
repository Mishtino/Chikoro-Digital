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


def test_school_admin_can_update_student_profile_and_audit_changes(client, seed_two_schools, db_session):
    data = seed_two_schools
    _set_principal(data["u1"], data["s1"].id)
    created = client.post("/students", json={
        "first_name": "Ada",
        "last_name": "Moyo",
        "form": "Form 1",
    })
    assert created.status_code == 201

    response = client.patch(f"/students/{created.json()['id']}", json={
        "first_name": "  Adah ",
        "form": " Form 2 ",
    })

    assert response.status_code == 200
    assert response.json()["first_name"] == "Adah"
    assert response.json()["last_name"] == "Moyo"
    assert response.json()["form"] == "Form 2"

    from app.models.audit import AuditLog
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "student.profile_update",
        AuditLog.entity_id == str(created.json()["id"]),
    ).order_by(AuditLog.id.desc()).first()
    assert audit is not None
    assert audit.details["changes"]["first_name"] == {"from": "Ada", "to": "Adah"}


def test_student_profile_update_rejects_blank_or_unknown_fields(client, seed_two_schools):
    data = seed_two_schools
    _set_principal(data["u1"], data["s1"].id)
    created = client.post("/students", json={"first_name": "Ada", "last_name": "Moyo"})
    student_id = created.json()["id"]

    blank = client.patch(f"/students/{student_id}", json={"first_name": "   "})
    protected = client.patch(f"/students/{student_id}", json={"student_number": "OTHER"})
    empty = client.patch(f"/students/{student_id}", json={})

    assert blank.status_code == 422
    assert protected.status_code == 422
    assert empty.status_code == 422


def test_student_profile_update_is_school_scoped_and_admin_only(client, seed_two_schools):
    data = seed_two_schools
    _set_principal(data["u1"], data["s1"].id)
    created = client.post("/students", json={"first_name": "Ada", "last_name": "Moyo"})
    student_id = created.json()["id"]

    _set_principal(data["u2"], data["s2"].id)
    cross_school = client.patch(f"/students/{student_id}", json={"form": "Form 4"})
    assert cross_school.status_code == 404

    teacher = data["u1"]
    _set_principal(teacher, data["s1"].id, role="teacher")
    forbidden = client.patch(f"/students/{student_id}", json={"form": "Form 4"})
    assert forbidden.status_code == 403


def test_student_directory_reports_portal_linkage_without_exposing_email(client, seed_two_schools):
    data = seed_two_schools
    _set_principal(data["u1"], data["s1"].id)

    without_portal = client.post("/students", json={
        "first_name": "No", "last_name": "Portal",
    })
    with_portal = client.post("/students", json={
        "first_name": "Has", "last_name": "Portal",
        "student_email": "learner.portal@example.com",
    })
    assert without_portal.status_code == 201
    assert with_portal.status_code == 201
    assert without_portal.json()["portal_enabled"] is False
    assert with_portal.json()["portal_enabled"] is True

    directory = client.get("/students")
    assert directory.status_code == 200
    rows = {row["id"]: row for row in directory.json()}
    assert rows[without_portal.json()["id"]]["portal_enabled"] is False
    assert rows[with_portal.json()["id"]]["portal_enabled"] is True
    assert "portal_email" not in rows[with_portal.json()["id"]]
