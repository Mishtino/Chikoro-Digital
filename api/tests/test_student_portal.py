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
