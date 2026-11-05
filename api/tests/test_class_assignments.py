from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.student import Student
from app.models.user import User
from app.services.auth import hash_password


def _principal(user, school, role=None, is_admin=False):
    return SupabasePrincipal(
        auth_user_id=uuid4(), user_id=user.id, school_id=school.id,
        role=role or user.role, is_admin=is_admin,
    )


def test_teacher_student_access_is_limited_to_assigned_classes(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    other_school = seed_two_schools["s2"]
    owner = seed_two_schools["u1"]
    teacher = User(
        email="class.teacher@example.com", full_name="Class Teacher",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=school.id, is_active=True, is_admin=False,
    )
    one = Student(
        school_id=school.id, student_number="CLS-001",
        first_name="One", last_name="Learner", form="Form 1", status="active",
    )
    two = Student(
        school_id=school.id, student_number="CLS-002",
        first_name="Two", last_name="Learner", form="Form 2", status="active",
    )
    db_session.add_all([teacher, one, two])
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(owner, school)

    assigned = client.post("/classes/assignments", json={
        "class_name": "Form 1", "teacher_user_id": teacher.id,
    })
    assert assigned.status_code == 201
    classes = client.get("/classes")
    assert {row["class_name"] for row in classes.json()} == {"Form 1", "Form 2"}

    app.dependency_overrides[get_supabase_principal] = lambda: _principal(teacher, school)
    directory = client.get("/students")
    assert directory.status_code == 200
    assert [row["form"] for row in directory.json()] == ["Form 1"]
    assert client.get(f"/students/{one.id}").status_code == 200
    assert client.get(f"/students/{two.id}").status_code == 404
    assert client.post("/students", json={"first_name": "No", "last_name": "Create"}).status_code == 403

    allowed_register = client.post("/attendance/sessions", json={
        "class_name": "Form 1", "attendance_date": "2026-11-05",
    })
    assert allowed_register.status_code == 201
    denied_register = client.post("/attendance/sessions", json={
        "class_name": "Form 2", "attendance_date": "2026-11-05",
    })
    assert denied_register.status_code == 403

    override = client.get("/students", params={"school_id": other_school.id})
    assert override.status_code == 403


def test_class_assignment_rejects_cross_school_teacher_and_teacher_cannot_manage(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    other = seed_two_schools["s2"]
    owner = seed_two_schools["u1"]
    learner = Student(
        school_id=school.id, student_number="CLS-003",
        first_name="Class", last_name="Learner", form="Form 3", status="active",
    )
    foreign_teacher = User(
        email="foreign.teacher@example.com", full_name="Foreign Teacher",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=other.id, is_active=True, is_admin=False,
    )
    db_session.add_all([learner, foreign_teacher])
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(owner, school)

    response = client.post("/classes/assignments", json={
        "class_name": "Form 3", "teacher_user_id": foreign_teacher.id,
    })
    assert response.status_code == 404

    teacher = User(
        email="teacher.nomanage@example.com", full_name="Teacher",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=school.id, is_active=True, is_admin=False,
    )
    db_session.add(teacher)
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(teacher, school)
    denied = client.post("/classes/assignments", json={
        "class_name": "Form 3", "teacher_user_id": teacher.id,
    })
    assert denied.status_code == 403


def test_teacher_can_enter_marks_only_for_assigned_class(client, db_session, seed_two_schools):
    from app.models.results import Assessment, Subject

    school = seed_two_schools["s1"]
    owner = seed_two_schools["u1"]
    teacher = User(
        email="marks.teacher@example.com", full_name="Marks Teacher",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=school.id, is_active=True, is_admin=False,
    )
    assigned_student = Student(
        school_id=school.id, student_number="MARK-CLS-1",
        first_name="Assigned", last_name="Learner", form="Form 1", status="active",
    )
    other_student = Student(
        school_id=school.id, student_number="MARK-CLS-2",
        first_name="Other", last_name="Learner", form="Form 2", status="active",
    )
    subject = Subject(school_id=school.id, name="Science", code="SCI")
    db_session.add_all([teacher, assigned_student, other_student, subject])
    db_session.flush()
    assessment = Assessment(
        school_id=school.id, subject_id=subject.id, name="Test",
        weight=1, max_score=100,
    )
    db_session.add(assessment)
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _principal(owner, school)
    assignment = client.post("/classes/assignments", json={
        "class_name": "Form 1", "teacher_user_id": teacher.id,
    })
    assert assignment.status_code == 201

    app.dependency_overrides[get_supabase_principal] = lambda: _principal(teacher, school)
    allowed = client.post("/results/marks", json={"entries": [{
        "student_id": assigned_student.id, "assessment_id": assessment.id, "score": 78,
    }]})
    assert allowed.status_code == 200
    denied = client.post("/results/marks", json={"entries": [{
        "student_id": other_student.id, "assessment_id": assessment.id, "score": 65,
    }]})
    assert denied.status_code == 403


def test_teacher_timetable_visibility_is_limited_to_assigned_classes(client, db_session, seed_two_schools):
    from datetime import time
    from app.models.fee import Term
    from app.models.results import Subject
    from app.models.timetable import TimetableEntry

    school = seed_two_schools["s1"]
    owner = seed_two_schools["u1"]
    teacher = User(
        email="timetable.teacher@example.com", full_name="Timetable Teacher",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=school.id, is_active=True, is_admin=False,
    )
    term = Term(school_id=school.id, name="Term 1", academic_year="2027")
    subject = Subject(school_id=school.id, name="History", code="HIST")
    db_session.add_all([teacher, term, subject])
    db_session.flush()
    db_session.add_all([
        TimetableEntry(
            school_id=school.id, term_id=term.id, subject_id=subject.id,
            class_name="Form 1", day_of_week=1, period_number=1,
            start_time=time(8, 0), end_time=time(8, 40), created_by_user_id=owner.id,
        ),
        TimetableEntry(
            school_id=school.id, term_id=term.id, subject_id=subject.id,
            class_name="Form 2", day_of_week=1, period_number=1,
            start_time=time(8, 0), end_time=time(8, 40), created_by_user_id=owner.id,
        ),
    ])
    learner = Student(
        school_id=school.id, student_number="TTS-001",
        first_name="Class", last_name="Learner", form="Form 1", status="active",
    )
    db_session.add(learner)
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _principal(owner, school)
    assert client.post("/classes/assignments", json={
        "class_name": "Form 1", "teacher_user_id": teacher.id,
    }).status_code == 201

    app.dependency_overrides[get_supabase_principal] = lambda: _principal(teacher, school)
    response = client.get("/timetable/entries")
    assert response.status_code == 200
    assert [row["class_name"] for row in response.json()] == ["Form 1"]
