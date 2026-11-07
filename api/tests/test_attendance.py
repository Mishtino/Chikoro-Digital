from datetime import date
from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.student import Student


def _principal(user, school, role="owner", is_admin=False):
    return SupabasePrincipal(
        auth_user_id=uuid4(), user_id=user.id, school_id=school.id,
        role=role, is_admin=is_admin,
    )


def test_attendance_register_requires_complete_class_roster(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    owner = seed_two_schools["u1"]
    first = Student(
        school_id=school.id, student_number="ATT-001",
        first_name="Ava", last_name="One", form="Form 1", status="active",
    )
    second = Student(
        school_id=school.id, student_number="ATT-002",
        first_name="Ben", last_name="Two", form="Form 1", status="active",
    )
    db_session.add_all([first, second])
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(owner, school)

    created = client.post("/attendance/sessions", json={
        "class_name": "Form 1", "attendance_date": "2026-11-05",
    })
    assert created.status_code == 201
    session_id = created.json()["id"]

    duplicate = client.post("/attendance/sessions", json={
        "class_name": "Form 1", "attendance_date": "2026-11-05",
    })
    assert duplicate.status_code == 409

    partial = client.put(f"/attendance/sessions/{session_id}/records", json={
        "entries": [{"student_id": first.id, "status": "present"}],
    })
    assert partial.status_code == 200
    incomplete = client.post(f"/attendance/sessions/{session_id}/submit")
    assert incomplete.status_code == 409
    assert "still need" in incomplete.json()["detail"]

    complete = client.put(f"/attendance/sessions/{session_id}/records", json={
        "entries": [
            {"student_id": first.id, "status": "present"},
            {"student_id": second.id, "status": "late", "note": "Arrived after assembly"},
        ],
    })
    assert complete.status_code == 200
    submitted = client.post(f"/attendance/sessions/{session_id}/submit")
    assert submitted.status_code == 200
    assert submitted.json()["learner_count"] == 2

    locked = client.put(f"/attendance/sessions/{session_id}/records", json={
        "entries": [{"student_id": first.id, "status": "absent"}],
    })
    assert locked.status_code == 409


def test_attendance_rejects_cross_school_learners_and_scope_override(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    other_school = seed_two_schools["s2"]
    owner = seed_two_schools["u1"]
    learner = Student(
        school_id=other_school.id, student_number="ATT-X01",
        first_name="Cross", last_name="School", form="Form 2", status="active",
    )
    db_session.add(learner)
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(owner, school)

    override = client.get("/attendance/sessions", params={"school_id": other_school.id})
    assert override.status_code == 403

    created = client.post("/attendance/sessions", json={
        "class_name": "Form 2", "attendance_date": "2026-11-05",
    })
    assert created.status_code == 201
    response = client.put(f"/attendance/sessions/{created.json()['id']}/records", json={
        "entries": [{"student_id": learner.id, "status": "present"}],
    })
    assert response.status_code == 422


def test_platform_admin_cannot_access_school_attendance(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=admin.id, school_id=None,
        role="vortex_admin", is_admin=True,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal
    response = client.get("/attendance/sessions", params={"school_id": seed_two_schools["s1"].id})
    assert response.status_code == 403


def test_attendance_rejects_duplicate_students_in_payload(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    owner = seed_two_schools["u1"]
    learner = Student(
        school_id=school.id, student_number="ATT-DUP",
        first_name="Double", last_name="Entry", form="Form 3", status="active",
    )
    db_session.add(learner)
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(owner, school)
    created = client.post("/attendance/sessions", json={
        "class_name": "Form 3", "attendance_date": "2026-11-05",
    })
    assert created.status_code == 201
    response = client.put(f"/attendance/sessions/{created.json()['id']}/records", json={
        "entries": [
            {"student_id": learner.id, "status": "present"},
            {"student_id": learner.id, "status": "absent"},
        ],
    })
    assert response.status_code == 422
