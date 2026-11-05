from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.class_assignment import ClassTeacherAssignment
from app.models.homework import HomeworkAssignment
from app.models.results import Subject
from app.models.student import Student
from app.models.user import User
from app.services.auth import hash_password


def _principal(user, school):
    return SupabasePrincipal(
        auth_user_id=uuid4(), user_id=user.id, school_id=school.id,
        role=user.role, is_admin=False,
    )


def test_homework_teacher_student_submission_and_marking(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    teacher = User(
        email="homework.teacher@example.com", full_name="Homework Teacher",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=school.id, is_active=True, is_admin=False,
    )
    learner_user = User(
        email="homework.student@example.com", full_name="Learner",
        password_hash=hash_password("test-password"), role="student",
        school_id=school.id, is_active=True, is_admin=False,
    )
    student = Student(
        school_id=school.id, student_number="HW-001", first_name="Tariro",
        last_name="Moyo", form="Form 1", status="active",
    )
    subject = Subject(school_id=school.id, name="Mathematics", code="MATH")
    db_session.add_all([teacher, learner_user, student, subject])
    db_session.flush()
    student.portal_user_id = learner_user.id
    db_session.add(ClassTeacherAssignment(
        school_id=school.id, class_name="Form 1", teacher_user_id=teacher.id,
        assigned_by_user_id=seed_two_schools["u1"].id, is_active=True,
    ))
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _principal(teacher, school)
    created = client.post("/homework/assignments", json={
        "class_name": "Form 1", "subject_id": subject.id,
        "title": "Fractions practice", "instructions": "Complete questions 1 to 10.",
        "publish": True,
    })
    assert created.status_code == 201
    assignment_id = created.json()["id"]

    app.dependency_overrides[get_supabase_principal] = lambda: _principal(learner_user, school)
    available = client.get("/homework/student/assignments")
    assert available.status_code == 200
    assert available.json()["assignments"][0]["submission_status"] == "not_submitted"

    submitted = client.post(
        f"/homework/student/assignments/{assignment_id}/submit",
        json={"answer_text": "My completed answers are 1 to 10."},
    )
    assert submitted.status_code == 201
    duplicate = client.post(
        f"/homework/student/assignments/{assignment_id}/submit",
        json={"answer_text": "Second attempt"},
    )
    assert duplicate.status_code == 409

    app.dependency_overrides[get_supabase_principal] = lambda: _principal(teacher, school)
    submissions = client.get(f"/homework/assignments/{assignment_id}/submissions")
    assert submissions.status_code == 200
    assert submissions.json()["submissions"][0]["student_id"] == student.id
    marked = client.post(
        f"/homework/submissions/{submitted.json()['id']}/mark",
        json={"feedback": "Good effort.", "score": 8},
    )
    assert marked.status_code == 200
    assert marked.json()["status"] == "marked"


def test_homework_teacher_cannot_create_for_unassigned_class(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    teacher = User(
        email="homework.unassigned@example.com", full_name="Unassigned Teacher",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=school.id, is_active=True, is_admin=False,
    )
    subject = Subject(school_id=school.id, name="English", code="ENG")
    db_session.add_all([teacher, subject])
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(teacher, school)

    response = client.post("/homework/assignments", json={
        "class_name": "Form 4", "subject_id": subject.id,
        "title": "Essay", "instructions": "Write an essay.",
    })
    assert response.status_code == 403


def test_homework_assignment_is_school_scoped(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    teacher = User(
        email="homework.scope@example.com", full_name="Scoped Teacher",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=school.id, is_active=True, is_admin=False,
    )
    subject = Subject(school_id=school.id, name="Science", code="SCI")
    db_session.add_all([teacher, subject])
    db_session.flush()
    db_session.add(ClassTeacherAssignment(
        school_id=school.id, class_name="Form 2", teacher_user_id=teacher.id,
        assigned_by_user_id=seed_two_schools["u1"].id, is_active=True,
    ))
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(teacher, school)

    response = client.post("/homework/assignments", json={
        "class_name": "Form 2", "subject_id": subject.id,
        "title": "Lab report", "instructions": "Describe the experiment.",
    })
    assert response.status_code == 201
