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
    from app.models.class_assignment import ClassTeacherAssignment

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
        form="Form 1",
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
    db_session.add(ClassTeacherAssignment(
        school_id=school.id, class_name="Form 1",
        teacher_user_id=principal.user_id,
        assigned_by_user_id=seed_two_schools["u1"].id, is_active=True,
    ))
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


def test_class_performance_analytics_only_uses_published_marks_and_respects_teacher_classes(
    client, db_session, seed_two_schools
):
    from app.models.student import Student
    from app.models.results import Mark
    from app.models.class_assignment import ClassTeacherAssignment

    school = seed_two_schools["s1"]
    teacher_user = seed_two_schools["u1"]
    term = Term(school_id=school.id, name="Term 2", academic_year="2026")
    subject = Subject(school_id=school.id, name="Mathematics", code="AN-MATH")
    db_session.add_all([term, subject])
    db_session.flush()

    form_one = Student(
        school_id=school.id, student_number="AN-001", first_name="Tariro",
        last_name="Moyo", form="Form 1", status="active",
    )
    form_two = Student(
        school_id=school.id, student_number="AN-002", first_name="Tendai",
        last_name="Ncube", form="Form 2", status="active",
    )
    db_session.add_all([form_one, form_two])
    db_session.flush()

    assessment = Assessment(
        school_id=school.id, subject_id=subject.id, term_id=term.id,
        name="End of term", weight=1, max_score=100,
    )
    db_session.add(assessment)
    db_session.flush()
    db_session.add_all([
        Mark(school_id=school.id, student_id=form_one.id, assessment_id=assessment.id,
             score=80, status="published", entered_by_user_id=teacher_user.id),
        Mark(school_id=school.id, student_id=form_two.id, assessment_id=assessment.id,
             score=20, status="published", entered_by_user_id=teacher_user.id),
        Mark(school_id=school.id, student_id=form_one.id, assessment_id=assessment.id,
             score=10, status="draft", entered_by_user_id=teacher_user.id),
    ])
    db_session.add(ClassTeacherAssignment(
        school_id=school.id, class_name="Form 1", teacher_user_id=teacher_user.id,
        assigned_by_user_id=teacher_user.id, is_active=True,
    ))
    db_session.commit()

    teacher = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=teacher_user.id,
        school_id=school.id, role="teacher", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: teacher
    response = client.get("/results/analytics/class-performance", params={"term_id": term.id})
    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    row = response.json()["results"][0]
    assert row["class_name"] == "Form 1"
    assert row["learner_count"] == 1
    assert row["mark_count"] == 1
    assert row["average_percent"] == 80
    assert row["pass_rate_percent"] == 100

    denied = client.get(
        "/results/analytics/class-performance",
        params={"term_id": term.id, "class_name": "Form 2"},
    )
    assert denied.status_code == 403

    owner = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=teacher_user.id,
        school_id=school.id, role="owner", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: owner
    all_classes = client.get("/results/analytics/class-performance", params={"term_id": term.id})
    assert all_classes.status_code == 200
    assert {row["class_name"] for row in all_classes.json()["results"]} == {"Form 1", "Form 2"}


def test_report_card_is_restricted_to_assigned_teacher_classes(client, db_session, seed_two_schools):
    from app.models.student import Student
    from app.models.results import Mark
    from app.models.class_assignment import ClassTeacherAssignment

    school = seed_two_schools["s1"]
    teacher_user = seed_two_schools["u1"]
    student = Student(
        school_id=school.id, student_number="RC-002", first_name="Nyasha",
        last_name="Dube", form="Form 2", status="active",
    )
    subject = Subject(school_id=school.id, name="English", code="RC-ENG")
    db_session.add_all([student, subject])
    db_session.flush()
    assessment = Assessment(
        school_id=school.id, subject_id=subject.id, name="Final",
        weight=1, max_score=100,
    )
    db_session.add(assessment)
    db_session.flush()
    db_session.add(Mark(
        school_id=school.id, student_id=student.id, assessment_id=assessment.id,
        score=88, status="published", entered_by_user_id=teacher_user.id,
    ))
    db_session.add(ClassTeacherAssignment(
        school_id=school.id, class_name="Form 1", teacher_user_id=teacher_user.id,
        assigned_by_user_id=teacher_user.id, is_active=True,
    ))
    db_session.commit()

    teacher = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=teacher_user.id,
        school_id=school.id, role="teacher", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: teacher
    denied = client.get(f"/results/report-card/{student.id}")
    assert denied.status_code == 403

    owner = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=teacher_user.id,
        school_id=school.id, role="owner", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: owner
    allowed = client.get(f"/results/report-card/{student.id}")
    assert allowed.status_code == 200
    assert allowed.json()["subjects"][0]["average"] == 88
