from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.fee import Term
from app.models.results import Subject
from app.models.user import User
from app.services.auth import hash_password


def _principal(user, school, role="owner", is_admin=False):
    return SupabasePrincipal(
        auth_user_id=uuid4(), user_id=user.id, school_id=school.id,
        role=role, is_admin=is_admin,
    )


def _setup_timetable(db_session, school):
    term = Term(school_id=school.id, name="Term 1", academic_year="2027")
    subject = Subject(school_id=school.id, name="Mathematics", code="MATH")
    teacher = User(
        email=f"teacher-{school.id}@test.com", full_name="Teacher One",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=school.id, is_active=True, is_admin=False,
    )
    db_session.add_all([term, subject, teacher])
    db_session.commit()
    return term, subject, teacher


def test_timetable_creation_and_conflict_checks(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    owner = seed_two_schools["u1"]
    term, subject, teacher = _setup_timetable(db_session, school)
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(owner, school)
    payload = {
        "term_id": term.id, "subject_id": subject.id, "teacher_user_id": teacher.id,
        "class_name": "Form 1", "day_of_week": 1, "period_number": 1,
        "start_time": "08:00", "end_time": "08:40", "room": "Room A",
    }
    created = client.post("/timetable/entries", json=payload)
    assert created.status_code == 201
    assert created.json()["id"]

    class_overlap = dict(payload, period_number=2, start_time="08:20", end_time="09:00", teacher_user_id=None, room="Room B")
    assert client.post("/timetable/entries", json=class_overlap).status_code == 409

    teacher_overlap = dict(payload, class_name="Form 2", period_number=1, start_time="08:10", end_time="08:30", room="Room B")
    assert client.post("/timetable/entries", json=teacher_overlap).status_code == 409

    room_overlap = dict(payload, class_name="Form 3", period_number=1, start_time="08:10", end_time="08:30", teacher_user_id=None)
    assert client.post("/timetable/entries", json=room_overlap).status_code == 409

    rows = client.get("/timetable/entries", params={"class_name": "Form 1"})
    assert rows.status_code == 200
    assert len(rows.json()) == 1
    assert rows.json()[0]["teacher_name"] == "Teacher One"


def test_timetable_rejects_cross_school_subject_teacher_and_scope(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    other = seed_two_schools["s2"]
    owner = seed_two_schools["u1"]
    other_term, other_subject, other_teacher = _setup_timetable(db_session, other)
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(owner, school)

    cross_school = client.post("/timetable/entries", json={
        "term_id": other_term.id, "subject_id": other_subject.id,
        "teacher_user_id": other_teacher.id, "class_name": "Form 1",
        "day_of_week": 1, "period_number": 1, "start_time": "08:00", "end_time": "08:40",
    })
    assert cross_school.status_code == 404
    override = client.get("/timetable/entries", params={"school_id": other.id})
    assert override.status_code == 403


def test_teacher_can_read_but_not_modify_timetable(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    owner = seed_two_schools["u1"]
    term, subject, teacher = _setup_timetable(db_session, school)
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(owner, school)
    created = client.post("/timetable/entries", json={
        "term_id": term.id, "subject_id": subject.id, "teacher_user_id": teacher.id,
        "class_name": "Form 1", "day_of_week": 2, "period_number": 1,
        "start_time": "09:00", "end_time": "09:40",
    })
    assert created.status_code == 201

    app.dependency_overrides[get_supabase_principal] = lambda: _principal(teacher, school, role="teacher")
    assert client.get("/timetable/entries").status_code == 200
    denied = client.post("/timetable/entries", json={
        "term_id": term.id, "subject_id": subject.id, "class_name": "Form 1",
        "day_of_week": 2, "period_number": 2, "start_time": "10:00", "end_time": "10:40",
    })
    assert denied.status_code == 403


def test_timetable_validates_day_and_time_range(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    owner = seed_two_schools["u1"]
    term, subject, _teacher = _setup_timetable(db_session, school)
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(owner, school)
    invalid = client.post("/timetable/entries", json={
        "term_id": term.id, "subject_id": subject.id, "class_name": "Form 1",
        "day_of_week": 8, "period_number": 1, "start_time": "11:00", "end_time": "10:00",
    })
    assert invalid.status_code == 422
