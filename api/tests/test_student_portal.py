from datetime import date
from uuid import uuid4

from fastapi import HTTPException

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.fee import Term
from app.models.results import Assessment, Mark, Subject
from app.models.school import School
from app.models.student import Student


def test_student_terms_only_return_published_terms_for_authenticated_learner(client, db_session):
    school = School(code="STU001", name="Student Portal School")
    other_school = School(code="STU002", name="Other School")
    db_session.add_all([school, other_school])
    db_session.flush()

    learner = Student(
        school_id=school.id, student_number="S-001",
        first_name="Tariro", last_name="Moyo", status="active",
        portal_user_id=7001,
    )
    other_learner = Student(
        school_id=school.id, student_number="S-002",
        first_name="Tawanda", last_name="Moyo", status="active",
        portal_user_id=7002,
    )
    db_session.add_all([learner, other_learner])
    db_session.flush()

    published = Term(school_id=school.id, name="Term 1", academic_year="2026",
                     start_date=date(2026, 1, 1), is_current=False)
    draft = Term(school_id=school.id, name="Term 2", academic_year="2026",
                 start_date=date(2026, 5, 1), is_current=True)
    other_tenant_term = Term(school_id=other_school.id, name="Term 1", academic_year="2026")
    db_session.add_all([published, draft, other_tenant_term])
    db_session.flush()

    subject = Subject(school_id=school.id, name="Mathematics")
    other_subject = Subject(school_id=other_school.id, name="English")
    db_session.add_all([subject, other_subject])
    db_session.flush()

    assessments = [
        Assessment(school_id=school.id, subject_id=subject.id, term_id=published.id,
                   name="Test 1", weight=1, max_score=100),
        Assessment(school_id=school.id, subject_id=subject.id, term_id=draft.id,
                   name="Test 2", weight=1, max_score=100),
        Assessment(school_id=other_school.id, subject_id=other_subject.id,
                   term_id=other_tenant_term.id, name="Other test", weight=1, max_score=100),
    ]
    db_session.add_all(assessments)
    db_session.flush()
    db_session.add_all([
        Mark(school_id=school.id, student_id=learner.id, assessment_id=assessments[0].id,
             score=80, status="published"),
        Mark(school_id=school.id, student_id=learner.id, assessment_id=assessments[1].id,
             score=90, status="draft"),
        Mark(school_id=school.id, student_id=other_learner.id, assessment_id=assessments[0].id,
             score=70, status="published"),
    ])
    db_session.commit()

    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=7001, school_id=school.id,
        role="student", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal
    response = client.get("/portal/terms")

    assert response.status_code == 200
    assert response.json()["terms"] == [{
        "id": published.id, "name": "Term 1", "academic_year": "2026",
        "is_current": False,
    }]


def test_student_terms_reject_non_student_role(client, db_session):
    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=7003, school_id=1,
        role="parent", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal
    response = client.get("/portal/terms")
    assert response.status_code == 403



def test_student_portal_fails_closed_when_account_maps_to_multiple_learners(client, db_session):
    school = School(code="STU003", name="Ambiguous Student Portal")
    db_session.add(school)
    db_session.flush()

    db_session.add_all([
        Student(
            school_id=school.id, student_number="AMB-001",
            first_name="First", last_name="Learner", status="active",
            portal_user_id=7100,
        ),
        Student(
            school_id=school.id, student_number="AMB-002",
            first_name="Second", last_name="Learner", status="active",
            portal_user_id=7100,
        ),
    ])
    db_session.commit()

    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=7100, school_id=school.id,
        role="student", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    fee_response = client.get("/portal/fee-status")
    results_response = client.get("/portal/results")

    assert fee_response.status_code == 403
    assert results_response.status_code == 403
    assert fee_response.json()["detail"] == "Student account is not uniquely linked"
    assert results_response.json()["detail"] == "Student account is not uniquely linked"


def test_student_portal_rejects_active_and_inactive_duplicate_mappings(client, db_session):
    school = School(code="STU004", name="Historical Mapping School")
    db_session.add(school)
    db_session.flush()
    db_session.add_all([
        Student(
            school_id=school.id, student_number="HIST-001",
            first_name="Active", last_name="Learner", status="active",
            portal_user_id=7200,
        ),
        Student(
            school_id=school.id, student_number="HIST-002",
            first_name="Inactive", last_name="Learner", status="inactive",
            portal_user_id=7200,
        ),
    ])
    db_session.commit()

    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=7200, school_id=school.id,
        role="student", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    responses = [
        client.get("/portal/fee-status"),
        client.get("/portal/terms"),
        client.get("/portal/results"),
    ]
    assert all(response.status_code == 403 for response in responses)
    assert all(
        response.json()["detail"] == "Student account is not uniquely linked"
        for response in responses
    )


def test_student_results_keep_same_named_subject_records_separate(client, db_session):
    school = School(code="STU005", name="Duplicate Subject Names")
    db_session.add(school)
    db_session.flush()
    learner = Student(
        school_id=school.id, student_number="DUP-001", first_name="Rudo",
        last_name="Moyo", status="active", portal_user_id=7300,
    )
    db_session.add(learner)
    db_session.flush()
    first = Subject(school_id=school.id, name="Mathematics", code="MATH-A")
    second = Subject(school_id=school.id, name="Mathematics", code="MATH-B")
    db_session.add_all([first, second])
    db_session.flush()
    assessments = [
        Assessment(school_id=school.id, subject_id=first.id, name="Paper 1", weight=1, max_score=100),
        Assessment(school_id=school.id, subject_id=second.id, name="Paper 2", weight=1, max_score=100),
    ]
    db_session.add_all(assessments)
    db_session.flush()
    db_session.add_all([
        Mark(school_id=school.id, student_id=learner.id, assessment_id=assessments[0].id,
             score=70, status="published"),
        Mark(school_id=school.id, student_id=learner.id, assessment_id=assessments[1].id,
             score=90, status="published"),
    ])
    db_session.commit()
    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=7300, school_id=school.id,
        role="student", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal
    response = client.get("/portal/results")
    assert response.status_code == 200
    assert len(response.json()["subjects"]) == 2
    assert {row["average"] for row in response.json()["subjects"]} == {70, 90}
    assert len({row["subject_id"] for row in response.json()["subjects"]}) == 2

def test_student_term_comparison_compares_only_published_marks(client, db_session):
    school = School(code="CMP001", name="Comparison School")
    db_session.add(school)
    db_session.flush()
    learner = Student(
        school_id=school.id, student_number="CMP-001", first_name="Tariro",
        last_name="Moyo", status="active", portal_user_id=7400,
    )
    db_session.add(learner)
    db_session.flush()
    older = Term(school_id=school.id, name="Term 1", academic_year="2026",
                 start_date=date(2026, 1, 1))
    newer = Term(school_id=school.id, name="Term 2", academic_year="2026",
                 start_date=date(2026, 5, 1))
    db_session.add_all([older, newer])
    db_session.flush()
    subject = Subject(school_id=school.id, name="Mathematics")
    db_session.add(subject)
    db_session.flush()
    old_assessment = Assessment(school_id=school.id, subject_id=subject.id,
                                term_id=older.id, name="Term 1 exam", weight=1, max_score=100)
    new_assessment = Assessment(school_id=school.id, subject_id=subject.id,
                                term_id=newer.id, name="Term 2 exam", weight=1, max_score=100)
    db_session.add_all([old_assessment, new_assessment])
    db_session.flush()
    db_session.add_all([
        Mark(school_id=school.id, student_id=learner.id, assessment_id=old_assessment.id,
             score=65, status="published"),
        Mark(school_id=school.id, student_id=learner.id, assessment_id=new_assessment.id,
             score=80, status="published"),
    ])
    db_session.commit()
    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=7400, school_id=school.id,
        role="student", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal
    response = client.get("/portal/results/comparison")
    assert response.status_code == 200
    data = response.json()
    assert data["current_term"]["id"] == newer.id
    assert data["previous_term"]["id"] == older.id
    assert data["subjects"] == [{
        "subject_id": subject.id, "subject": "Mathematics",
        "current_average": 80.0, "previous_average": 65.0, "change": 15.0,
    }]

