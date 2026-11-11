"""Classroom access regression tests (no video provider or network needed)."""
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.deps_supabase import SupabasePrincipal
from app.models.class_assignment import ClassTeacherAssignment
from app.models.student import Student
from app.models.user import User
from app.services.classroom_access import require_classroom_host, require_classroom_student


def principal(user):
    return SupabasePrincipal(UUID(int=user.id), user.id, user.school_id, user.role, user.is_admin)


def expect_denied(fn, *args):
    with pytest.raises(HTTPException) as exc:
        fn(*args)
    assert exc.value.status_code == 403


def test_teacher_must_be_active_and_assigned(db_session, seed_two_schools):
    a, b = seed_two_schools["s1"], seed_two_schools["s2"]
    teacher = User(email="classroom.teacher@test.invalid", full_name="Teacher",
                   password_hash="unused", role="teacher", school_id=a.id, is_active=True)
    db_session.add(teacher)
    db_session.flush()
    assignment = ClassTeacherAssignment(school_id=a.id, class_name="Form 4A",
        teacher_user_id=teacher.id, assigned_by_user_id=seed_two_schools["u1"].id, is_active=True)
    db_session.add(assignment)
    db_session.commit()
    require_classroom_host(db_session, principal(teacher), a.id, "Form 4A")
    expect_denied(require_classroom_host, db_session, principal(teacher), b.id, "Form 4A")
    expect_denied(require_classroom_host, db_session, principal(teacher), a.id, "Form 3B")
    assignment.is_active = False
    db_session.commit()
    expect_denied(require_classroom_host, db_session, principal(teacher), a.id, "Form 4A")
    assignment.is_active = True
    teacher.is_active = False
    db_session.commit()
    expect_denied(require_classroom_host, db_session, principal(teacher), a.id, "Form 4A")
    expect_denied(require_classroom_host, db_session, principal(seed_two_schools["admin"]), a.id, "Form 4A")


def test_student_must_have_active_portal_enrolment(db_session, seed_two_schools):
    a, b = seed_two_schools["s1"], seed_two_schools["s2"]
    user = User(email="classroom.student@test.invalid", full_name="Student",
                password_hash="unused", role="student", school_id=a.id, is_active=True)
    db_session.add(user)
    db_session.flush()
    student = Student(school_id=a.id, student_number="VC-001",
        first_name="Learner", last_name="One", form="Form 4A",
        status="active", portal_user_id=user.id)
    db_session.add(student)
    db_session.commit()
    assert require_classroom_student(db_session, principal(user), a.id, "Form 4A") == student.id
    expect_denied(require_classroom_student, db_session, principal(user), b.id, "Form 4A")
    expect_denied(require_classroom_student, db_session, principal(user), a.id, "Form 5A")
    student.status = "inactive"
    db_session.commit()
    expect_denied(require_classroom_student, db_session, principal(user), a.id, "Form 4A")
    student.status = "active"
    user.is_active = False
    db_session.commit()
    expect_denied(require_classroom_student, db_session, principal(user), a.id, "Form 4A")
    expect_denied(require_classroom_student, db_session, principal(seed_two_schools["admin"]), a.id, "Form 4A")
