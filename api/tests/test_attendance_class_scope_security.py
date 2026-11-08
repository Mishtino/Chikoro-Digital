from datetime import date
from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.attendance import AttendanceSession
from app.models.class_assignment import ClassTeacherAssignment
from app.models.student import Student
from app.services.auth import hash_password
from app.models.user import User


def _teacher_principal(user, school):
    return SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=user.id,
        school_id=school.id,
        role="teacher",
        is_admin=False,
    )


def test_unassigned_teacher_cannot_create_attendance_session(
    client, db_session, seed_two_schools
):
    school = seed_two_schools["s1"]
    teacher = User(
        email="attendance.unassigned@example.com",
        full_name="Unassigned Teacher",
        password_hash=hash_password("test-password"),
        role="teacher",
        school_id=school.id,
        is_active=True,
        is_admin=False,
    )
    db_session.add(teacher)
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _teacher_principal(teacher, school)

    response = client.post("/attendance/sessions", json={
        "class_name": "Form 1",
        "attendance_date": "2026-11-05",
    })
    assert response.status_code == 403


def test_teacher_cannot_read_attendance_for_unassigned_class(
    client, db_session, seed_two_schools
):
    school = seed_two_schools["s1"]
    teacher = User(
        email="attendance.classscope@example.com",
        full_name="Form One Teacher",
        password_hash=hash_password("test-password"),
        role="teacher",
        school_id=school.id,
        is_active=True,
        is_admin=False,
    )
    db_session.add(teacher)
    db_session.flush()
    db_session.add(ClassTeacherAssignment(
        school_id=school.id,
        class_name="Form 1",
        teacher_user_id=teacher.id,
        assigned_by_user_id=seed_two_schools["u1"].id,
        is_active=True,
    ))
    allowed = AttendanceSession(
        school_id=school.id,
        class_name="Form 1",
        attendance_date=date(2026, 11, 4),
        recorded_by_user_id=seed_two_schools["u1"].id,
        status="draft",
    )
    restricted = AttendanceSession(
        school_id=school.id,
        class_name="Form 2",
        attendance_date=date(2026, 11, 4),
        recorded_by_user_id=seed_two_schools["u1"].id,
        status="draft",
    )
    db_session.add_all([allowed, restricted])
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _teacher_principal(teacher, school)

    allowed_response = client.get(f"/attendance/sessions/{allowed.id}/records")
    assert allowed_response.status_code == 200

    restricted_response = client.get(f"/attendance/sessions/{restricted.id}/records")
    assert restricted_response.status_code == 403
