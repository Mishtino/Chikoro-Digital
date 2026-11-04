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
