from datetime import date
from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.fee import Term
from app.models.results import Assessment, Mark, Subject
from app.models.school import School
from app.models.student import Student
from app.routers import portal


def test_parent_terms_only_include_published_terms_for_selected_learner(client, db_session, monkeypatch):
    school = School(code="PAR001", name="Parent Portal School")
    other_school = School(code="PAR002", name="Other School")
    db_session.add_all([school, other_school])
    db_session.flush()

    learner = Student(
        school_id=school.id, student_number="P-001",
        first_name="Tariro", last_name="Moyo", status="active",
    )
    another_learner = Student(
        school_id=school.id, student_number="P-002",
        first_name="Tawanda", last_name="Moyo", status="active",
    )
    db_session.add_all([learner, another_learner])
    db_session.flush()

    published_term = Term(
        school_id=school.id, name="Term 2", academic_year="2026",
        start_date=date(2026, 5, 1), is_current=True,
    )
    draft_term = Term(
        school_id=school.id, name="Term 3", academic_year="2026",
        start_date=date(2026, 9, 1), is_current=False,
    )
    other_school_term = Term(
        school_id=other_school.id, name="Term 2", academic_year="2026",
        start_date=date(2026, 5, 1), is_current=True,
    )
    db_session.add_all([published_term, draft_term, other_school_term])
    db_session.flush()

    subject = Subject(school_id=school.id, name="Mathematics")
    other_subject = Subject(school_id=other_school.id, name="English")
    db_session.add_all([subject, other_subject])
    db_session.flush()

    assessments = [
        Assessment(school_id=school.id, subject_id=subject.id, term_id=published_term.id, name="Test 1", weight=1, max_score=100),
        Assessment(school_id=school.id, subject_id=subject.id, term_id=draft_term.id, name="Test 2", weight=1, max_score=100),
        Assessment(school_id=other_school.id, subject_id=other_subject.id, term_id=other_school_term.id, name="Other test", weight=1, max_score=100),
    ]
    db_session.add_all(assessments)
    db_session.flush()
    db_session.add_all([
        Mark(school_id=school.id, student_id=learner.id, assessment_id=assessments[0].id, score=80, status="published"),
        Mark(school_id=school.id, student_id=learner.id, assessment_id=assessments[1].id, score=90, status="draft"),
        Mark(school_id=school.id, student_id=another_learner.id, assessment_id=assessments[0].id, score=75, status="published"),
    ])
    db_session.commit()

    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=9001, school_id=school.id,
        role="parent", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    def verified_link_only(_principal, student_id, _db):
        if student_id != learner.id:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Linked student not found")
        return learner

    monkeypatch.setattr(portal, "_parent_student", verified_link_only)
    response = client.get(f"/portal/parent/children/{learner.id}/terms")

    assert response.status_code == 200
    assert response.json()["terms"] == [{
        "id": published_term.id,
        "name": "Term 2",
        "academic_year": "2026",
        "is_current": True,
    }]



def test_parent_student_ids_rejects_non_parent_and_missing_school_context():
    from fastapi import HTTPException
    import pytest

    class UnusedDB:
        def execute(self, *_args, **_kwargs):
            pytest.fail("Database must not be queried for an invalid parent context")

    non_parent = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=9002, school_id=1,
        role="student", is_admin=False,
    )
    with pytest.raises(HTTPException) as role_error:
        portal._parent_student_ids(non_parent, UnusedDB())
    assert role_error.value.status_code == 403

    no_school = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=9003, school_id=None,
        role="parent", is_admin=False,
    )
    with pytest.raises(HTTPException) as school_error:
        portal._parent_student_ids(no_school, UnusedDB())
    assert school_error.value.status_code == 403


def test_parent_student_ids_require_active_verified_same_school_guardian_link():
    from uuid import uuid4

    profile_id = uuid4()
    school_id = 42
    principal = SupabasePrincipal(
        auth_user_id=profile_id, user_id=9004, school_id=school_id,
        role="parent", is_admin=False,
    )

    class Result:
        def all(self):
            return [(123,), (456,)]

    class RecordingDB:
        statement = None
        params = None

        def execute(self, statement, params):
            self.statement = str(statement).lower()
            self.params = params
            return Result()

    db = RecordingDB()
    assert portal._parent_student_ids(principal, db) == [123, 456]
    assert db.params == {
        "profile_id": str(profile_id),
        "school_id": school_id,
    }
    # Guard the authorization query against accidental removal of any
    # tenant, active-link, verification, or active-learner restriction.
    for required_clause in (
        "gl.profile_id = :profile_id",
        "gl.school_id = :school_id",
        "gl.is_active = true",
        "gl.verified_at is not null",
        "s.status = 'active'",
        "c.school_id = gl.school_id",
        "s.school_id = c.school_id",
    ):
        assert required_clause in db.statement
