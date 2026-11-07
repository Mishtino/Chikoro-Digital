from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.fee import Term


def test_teacher_can_read_only_own_school_terms(client, seed_two_schools, db_session):
    own_school = seed_two_schools["s1"]
    other_school = seed_two_schools["s2"]
    teacher = seed_two_schools["u1"]
    db_session.add_all([
        Term(school_id=own_school.id, name="Teacher Term", academic_year="2027"),
        Term(school_id=other_school.id, name="Other School Term", academic_year="2027"),
    ])
    db_session.commit()
    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=teacher.id,
        school_id=own_school.id,
        role="teacher",
        is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.get("/fees/terms")
    assert response.status_code == 200
    assert [row["name"] for row in response.json()] == ["Teacher Term"]

    cross_school = client.get(f"/fees/terms?school_id={other_school.id}")
    assert cross_school.status_code == 403
