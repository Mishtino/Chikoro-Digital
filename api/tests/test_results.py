from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.fee import Term
from app.models.results import Assessment, Subject


def test_assessment_term_filter_is_school_scoped(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=seed_two_schools["u1"].id,
        school_id=school.id,
        role="teacher",
        is_admin=False,
    )
    term = Term(school_id=school.id, name="Term 1", academic_year="2026")
    other_term = Term(
        school_id=seed_two_schools["s2"].id,
        name="Term 1",
        academic_year="2026",
    )
    db_session.add_all([term, other_term])
    db_session.flush()
    subject = Subject(school_id=school.id, name="Mathematics", code="MATH")
    db_session.add(subject)
    db_session.flush()
    assessment = Assessment(
        school_id=school.id,
        subject_id=subject.id,
        term_id=term.id,
        name="Test 1",
        weight=1,
        max_score=100,
    )
    db_session.add(assessment)
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.get("/results/assessments", params={"term_id": term.id})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [assessment.id]

    response = client.get("/results/assessments", params={"term_id": other_term.id})
    assert response.status_code == 404

def test_bulk_marks_reject_duplicate_learner_assessment_pairs(client, seed_two_schools):
    school = seed_two_schools["s1"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=seed_two_schools["u1"].id,
        school_id=school.id,
        role="teacher",
        is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.post(
        "/results/marks",
        json={
            "entries": [
                {"student_id": 101, "assessment_id": 202, "score": 75},
                {"student_id": 101, "assessment_id": 202, "score": 80},
            ]
        },
    )

    assert response.status_code == 422
    assert "one mark per assessment" in response.json()["detail"]


def test_bulk_marks_allow_same_learner_in_different_assessments(client, seed_two_schools, db_session):
    from app.models.student import Student

    school = seed_two_schools["s1"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=seed_two_schools["u1"].id,
        school_id=school.id,
        role="teacher",
        is_admin=False,
    )
    student = Student(
        school_id=school.id,
        student_number="ST-RESULTS-001",
        first_name="Tariro",
        last_name="Moyo",
        status="active",
    )
    subject = Subject(school_id=school.id, name="Mathematics", code="MATH")
    db_session.add_all([student, subject])
    db_session.flush()
    assessment_one = Assessment(
        school_id=school.id, subject_id=subject.id, name="Test 1", weight=1, max_score=100
    )
    assessment_two = Assessment(
        school_id=school.id, subject_id=subject.id, name="Test 2", weight=1, max_score=100
    )
    db_session.add_all([assessment_one, assessment_two])
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.post(
        "/results/marks",
        json={
            "entries": [
                {"student_id": student.id, "assessment_id": assessment_one.id, "score": 75},
                {"student_id": student.id, "assessment_id": assessment_two.id, "score": 80},
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["saved"] == 2


def test_mark_review_is_school_scoped_and_teacher_sees_only_own_entries(
    client, db_session, seed_two_schools
):
    from app.models.student import Student
    from app.models.results import Mark

    school = seed_two_schools["s1"]
    teacher_user = seed_two_schools["u1"]
    other_user = seed_two_schools["u2"]
    student = Student(
        school_id=school.id,
        student_number="ST-MARK-REVIEW-001",
        first_name="Review",
        last_name="Learner",
        status="active",
    )
    subject = Subject(school_id=school.id, name="English", code="ENG")
    db_session.add_all([student, subject])
    db_session.flush()
    assessment_one = Assessment(
        school_id=school.id, subject_id=subject.id, name="Essay",
        weight=1, max_score=100,
    )
    assessment_two = Assessment(
        school_id=school.id, subject_id=subject.id, name="Reading",
        weight=1, max_score=100,
    )
    db_session.add_all([assessment_one, assessment_two])
    db_session.flush()
    db_session.add_all([
        Mark(
            school_id=school.id, student_id=student.id,
            assessment_id=assessment_one.id, score=75,
            entered_by_user_id=teacher_user.id,
        ),
        Mark(
            school_id=school.id, student_id=student.id,
            assessment_id=assessment_two.id, score=80,
            entered_by_user_id=other_user.id,
        ),
    ])
    db_session.commit()

    teacher = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=teacher_user.id,
        school_id=school.id, role="teacher", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: teacher
    response = client.get("/results/marks")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["assessment_name"] == "Essay"

    cross_school = client.get("/results/marks", params={"school_id": seed_two_schools["s2"].id})
    assert cross_school.status_code == 403

    owner = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=teacher_user.id,
        school_id=school.id, role="owner", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: owner
    owner_response = client.get("/results/marks")
    assert owner_response.status_code == 200
    assert len(owner_response.json()) == 2


def test_platform_admin_cannot_use_school_mark_review_endpoint(client, seed_two_schools):
    admin = seed_two_schools["admin"]
    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=admin.id,
        school_id=None, role="vortex_admin", is_admin=True,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal
    response = client.get("/results/marks", params={"school_id": seed_two_schools["s1"].id})
    assert response.status_code == 403
