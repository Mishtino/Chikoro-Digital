from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.class_assignment import ClassTeacherAssignment
from app.models.student import Student
from app.models.user import User


def _principal(user, school, role="owner"):
    return SupabasePrincipal(
        auth_user_id=uuid4(), user_id=user.id, school_id=school.id,
        role=role, is_admin=False,
    )


def test_class_assignment_rejects_teacher_from_another_school(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    other = seed_two_schools["s2"]
    owner = seed_two_schools["u1"]
    foreign_teacher = User(
        email="foreign.teacher@test.com", full_name="Foreign Teacher",
        password_hash="unused", role="teacher", school_id=other.id,
    )
    learner = Student(
        school_id=school.id, student_number="CLS-001",
        first_name="Ava", last_name="One", form="Form 1", status="active",
    )
    db_session.add_all([foreign_teacher, learner])
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(owner, school)

    response = client.post("/classes/assignments", json={
        "class_name": "Form 1", "teacher_user_id": foreign_teacher.id,
    })
    assert response.status_code == 404
    assert db_session.query(ClassTeacherAssignment).filter(
        ClassTeacherAssignment.school_id == school.id,
    ).count() == 0


def test_class_assignment_id_from_another_school_cannot_be_removed(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    other = seed_two_schools["s2"]
    owner = seed_two_schools["u1"]
    foreign_teacher = User(
        email="foreign.remove@test.com", full_name="Foreign Teacher",
        password_hash="unused", role="teacher", school_id=other.id,
    )
    db_session.add(foreign_teacher)
    db_session.flush()
    assignment = ClassTeacherAssignment(
        school_id=other.id, class_name="Form 2",
        teacher_user_id=foreign_teacher.id, assigned_by_user_id=foreign_teacher.id,
        is_active=True,
    )
    db_session.add(assignment)
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(owner, school)

    response = client.delete(f"/classes/assignments/{assignment.id}")
    assert response.status_code == 404
    db_session.refresh(assignment)
    assert assignment.is_active is True


def test_teacher_can_only_list_own_class_assignments(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    teacher = User(
        email="assigned.teacher@test.com", full_name="Assigned Teacher",
        password_hash="unused", role="teacher", school_id=school.id,
    )
    db_session.add(teacher)
    db_session.flush()
    own = ClassTeacherAssignment(
        school_id=school.id, class_name="Form 1",
        teacher_user_id=teacher.id, assigned_by_user_id=seed_two_schools["u1"].id,
        is_active=True,
    )
    another = ClassTeacherAssignment(
        school_id=school.id, class_name="Form 2",
        teacher_user_id=seed_two_schools["u1"].id, assigned_by_user_id=seed_two_schools["u1"].id,
        is_active=True,
    )
    db_session.add_all([own, another])
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(teacher, school, "teacher")

    response = client.get("/classes/assignments")
    assert response.status_code == 200
    assert [row["class_name"] for row in response.json()] == ["Form 1"]
