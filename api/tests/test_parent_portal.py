from datetime import date
from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.fee import Term
from app.models.results import Assessment, Mark, Subject
from app.models.school import School
from app.models.student import Student
from app.routers import portal


def _reset_sqlite_public_schema(db_session):
    """Prepare the attached SQLite schema used to mirror Supabase public tables."""
    from sqlalchemy import text

    attached = {
        row[1] for row in db_session.execute(text("PRAGMA database_list")).all()
    }
    if "public" not in attached:
        db_session.execute(text("ATTACH DATABASE ':memory:' AS public"))

    for table in ("guardian_links", "contacts", "students"):
        db_session.execute(text(f"DROP TABLE IF EXISTS public.{table}"))
    db_session.execute(text("""
        CREATE TABLE public.contacts AS
        SELECT id, school_id, student_id FROM contacts
    """))
    db_session.execute(text("""
        CREATE TABLE public.students AS
        SELECT id, school_id, status FROM students
    """))
    db_session.execute(text("""
        CREATE TABLE public.guardian_links (
            profile_id TEXT NOT NULL,
            contact_id INTEGER NOT NULL,
            school_id INTEGER NOT NULL,
            is_active BOOLEAN NOT NULL,
            verified_at TEXT
        )
    """))



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


def test_parent_attendance_shows_only_submitted_records_for_verified_child(client, db_session, seed_two_schools, monkeypatch):
    from datetime import date
    from app.models.attendance import AttendanceSession, AttendanceRecord

    school = seed_two_schools["s1"]
    owner = seed_two_schools["u1"]
    learner = Student(
        school_id=school.id, student_number="ATT-P-001",
        first_name="Rudo", last_name="Moyo", form="Form 2", status="active",
    )
    db_session.add(learner)
    db_session.flush()

    yesterday = AttendanceSession(
        school_id=school.id, class_name="Form 2", attendance_date=date(2026, 11, 4),
        status="submitted", recorded_by_user_id=owner.id,
    )
    today = AttendanceSession(
        school_id=school.id, class_name="Form 2", attendance_date=date(2026, 11, 5),
        status="submitted", recorded_by_user_id=owner.id,
    )
    draft = AttendanceSession(
        school_id=school.id, class_name="Form 2", attendance_date=date(2026, 11, 6),
        status="draft", recorded_by_user_id=owner.id,
    )
    db_session.add_all([yesterday, today, draft])
    db_session.flush()
    db_session.add_all([
        AttendanceRecord(
            school_id=school.id, session_id=yesterday.id, student_id=learner.id,
            status="present", marked_by_user_id=owner.id,
        ),
        AttendanceRecord(
            school_id=school.id, session_id=today.id, student_id=learner.id,
            status="late", note="Arrived after assembly", marked_by_user_id=owner.id,
        ),
        AttendanceRecord(
            school_id=school.id, session_id=draft.id, student_id=learner.id,
            status="absent", marked_by_user_id=owner.id,
        ),
    ])
    db_session.commit()

    parent = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=9101, school_id=school.id,
        role="parent", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: parent
    def verified_child(_principal, student_id, _db):
        from fastapi import HTTPException
        if student_id != learner.id:
            raise HTTPException(status_code=404, detail="Linked student not found")
        return learner
    monkeypatch.setattr(portal, "_parent_student", verified_child)

    response = client.get(f"/portal/parent/children/{learner.id}/attendance")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == {
        "total_recorded_days": 2, "present": 1, "absent": 0,
        "late": 1, "excused": 0, "attendance_rate": 100.0,
    }
    assert [row["status"] for row in data["records"]] == ["late", "present"]
    assert data["records"][0]["note"] == "Arrived after assembly"

    filtered = client.get(
        f"/portal/parent/children/{learner.id}/attendance",
        params={"from_date": "2026-11-05", "to_date": "2026-11-05"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["summary"]["total_recorded_days"] == 1


def test_parent_attendance_rejects_unlinked_child_and_invalid_date_range(client, db_session, seed_two_schools, monkeypatch):
    from datetime import date
    from fastapi import HTTPException
    from app.models.attendance import AttendanceSession, AttendanceRecord

    school = seed_two_schools["s1"]
    owner = seed_two_schools["u1"]
    learner = Student(
        school_id=school.id, student_number="ATT-P-002",
        first_name="Tariro", last_name="Moyo", status="active",
    )
    db_session.add(learner)
    db_session.flush()
    session = AttendanceSession(
        school_id=school.id, class_name="Form 1", attendance_date=date(2026, 11, 5),
        status="submitted", recorded_by_user_id=owner.id,
    )
    db_session.add(session)
    db_session.flush()
    db_session.add(AttendanceRecord(
        school_id=school.id, session_id=session.id, student_id=learner.id,
        status="absent", marked_by_user_id=owner.id,
    ))
    db_session.commit()

    parent = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=9102, school_id=school.id,
        role="parent", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: parent
    def verified_child(_principal, student_id, _db):
        if student_id != learner.id:
            raise HTTPException(status_code=404, detail="Linked student not found")
        return learner
    monkeypatch.setattr(portal, "_parent_student", verified_child)

    invalid = client.get(
        f"/portal/parent/children/{learner.id}/attendance",
        params={"from_date": "2026-11-06", "to_date": "2026-11-05"},
    )
    assert invalid.status_code == 422
    unlinked = client.get("/portal/parent/children/999999/attendance")
    assert unlinked.status_code == 404

def test_parent_term_comparison_is_scoped_to_verified_child(client, db_session, monkeypatch):
    school = School(code="PCMP1", name="Parent Comparison")
    db_session.add(school)
    db_session.flush()
    learner = Student(
        school_id=school.id, student_number="PCMP-001", first_name="Rudo",
        last_name="Moyo", status="active",
    )
    db_session.add(learner)
    db_session.flush()
    term1 = Term(school_id=school.id, name="Term 1", academic_year="2026",
                 start_date=date(2026, 1, 1))
    term2 = Term(school_id=school.id, name="Term 2", academic_year="2026",
                 start_date=date(2026, 5, 1))
    db_session.add_all([term1, term2])
    db_session.flush()
    subject = Subject(school_id=school.id, name="English")
    db_session.add(subject)
    db_session.flush()
    assessments = [
        Assessment(school_id=school.id, subject_id=subject.id, term_id=term1.id,
                   name="Term 1", weight=1, max_score=100),
        Assessment(school_id=school.id, subject_id=subject.id, term_id=term2.id,
                   name="Term 2", weight=1, max_score=100),
    ]
    db_session.add_all(assessments)
    db_session.flush()
    db_session.add_all([
        Mark(school_id=school.id, student_id=learner.id, assessment_id=assessments[0].id,
             score=55, status="published"),
        Mark(school_id=school.id, student_id=learner.id, assessment_id=assessments[1].id,
             score=75, status="published"),
    ])
    db_session.commit()
    parent = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=9200, school_id=school.id,
        role="parent", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: parent
    monkeypatch.setattr(portal, "_parent_student", lambda _principal, student_id, _db: learner if student_id == learner.id else None)
    response = client.get(f"/portal/parent/children/{learner.id}/results/comparison")
    assert response.status_code == 200
    assert response.json()["subjects"][0]["change"] == 20.0

def test_verified_parent_can_download_linked_child_report_card_pdf(client, db_session):
    from sqlalchemy import text
    from app.models.student import Contact

    school = School(code="PARPDF1", name="Parent PDF School")
    db_session.add(school)
    db_session.flush()
    learner = Student(school_id=school.id, student_number="PAR-PDF-1",
                      first_name="Tariro", last_name="Moyo", status="active")
    unlinked_learner = Student(school_id=school.id, student_number="PAR-PDF-2",
                               first_name="Tawanda", last_name="Moyo", status="active")
    subject = Subject(school_id=school.id, name="English")
    db_session.add_all([learner, unlinked_learner, subject])
    db_session.flush()
    contact = Contact(school_id=school.id, student_id=learner.id,
                       name="Verified parent", relationship="parent", is_primary=True)
    db_session.add(contact)
    assessment = Assessment(school_id=school.id, subject_id=subject.id,
                            name="Final", weight=1, max_score=100)
    db_session.add(assessment)
    db_session.flush()
    db_session.add(Mark(school_id=school.id, student_id=learner.id,
                        assessment_id=assessment.id, score=77, status="published"))
    profile_id = uuid4()
    db_session.commit()

    # Exercise the real guardian-link authorization query at the PDF route,
    # not a mocked _parent_student helper. Reuse the shared connection's
    # attached schema if another test has already created it.
    _reset_sqlite_public_schema(db_session)
    db_session.execute(text("""
        INSERT INTO public.guardian_links
            (profile_id, contact_id, school_id, is_active, verified_at)
        VALUES (:profile, :contact, :school, true, '2026-11-05T10:00:00Z')
    """), {"profile": str(profile_id), "contact": contact.id, "school": school.id})

    parent = SupabasePrincipal(auth_user_id=profile_id, user_id=9300,
                                school_id=school.id, role="parent", is_admin=False)
    app.dependency_overrides[get_supabase_principal] = lambda: parent
    response = client.get(f"/portal/parent/children/{learner.id}/report-card.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content.startswith(b"%PDF")

    # Same-school siblings are not implicitly visible without their own
    # verified guardian link; an unknown learner ID is also hidden.
    unlinked = client.get(f"/portal/parent/children/{unlinked_learner.id}/report-card.pdf")
    assert unlinked.status_code == 404
    denied = client.get("/portal/parent/children/999999/report-card.pdf")
    assert denied.status_code == 404


def test_parent_student_ids_resolve_only_real_active_verified_guardian_links(
    db_session, seed_two_schools
):
    """Exercise the real guardian-link SQL against same-school contact/learner rows."""
    from sqlalchemy import text
    from app.models.student import Contact

    school = seed_two_schools["s1"]
    other_school = seed_two_schools["s2"]
    profile_id = uuid4()

    valid = Student(
        school_id=school.id, student_number="GL-VALID-001",
        first_name="Valid", last_name="Learner", status="active",
    )
    inactive_learner = Student(
        school_id=school.id, student_number="GL-INACTIVE-001",
        first_name="Inactive", last_name="Learner", status="active",
    )
    unverified_learner = Student(
        school_id=school.id, student_number="GL-UNVERIFIED-001",
        first_name="Unverified", last_name="Learner", status="active",
    )
    other_school_learner = Student(
        school_id=other_school.id, student_number="GL-OTHER-SCHOOL-001",
        first_name="Other", last_name="School", status="active",
    )
    db_session.add_all([valid, inactive_learner, unverified_learner, other_school_learner])
    db_session.flush()

    contacts = [
        Contact(school_id=school.id, student_id=valid.id, name="Verified guardian",
                relationship="parent", is_primary=True),
        Contact(school_id=school.id, student_id=inactive_learner.id, name="Inactive guardian",
                relationship="parent", is_primary=True),
        Contact(school_id=school.id, student_id=unverified_learner.id, name="Unverified guardian",
                relationship="parent", is_primary=True),
        Contact(school_id=other_school.id, student_id=other_school_learner.id,
                name="Other school guardian", relationship="parent", is_primary=True),
    ]
    db_session.add_all(contacts)
    db_session.flush()

    # Mirror Supabase's schema-qualified tables in SQLite. Reuse an existing
    # attachment on the shared in-memory connection and reset its fixture data.
    _reset_sqlite_public_schema(db_session)
    db_session.execute(text("""
        INSERT INTO public.guardian_links
            (profile_id, contact_id, school_id, is_active, verified_at)
        VALUES
            (:profile, :valid_contact, :school, true, '2026-11-05T10:00:00Z'),
            (:profile, :inactive_contact, :school, false, '2026-11-05T10:00:00Z'),
            (:profile, :unverified_contact, :school, true, NULL),
            (:profile, :other_contact, :other_school, true, '2026-11-05T10:00:00Z')
    """), {
        "profile": str(profile_id),
        "valid_contact": contacts[0].id,
        "inactive_contact": contacts[1].id,
        "unverified_contact": contacts[2].id,
        "other_contact": contacts[3].id,
        "school": school.id,
        "other_school": other_school.id,
    })
    db_session.flush()

    parent = SupabasePrincipal(
        auth_user_id=profile_id, user_id=9400, school_id=school.id,
        role="parent", is_admin=False,
    )
    assert portal._parent_student_ids(parent, db_session) == [valid.id]
    assert portal._parent_student(parent, valid.id, db_session).id == valid.id

    from fastapi import HTTPException
    import pytest
    with pytest.raises(HTTPException) as inactive_link:
        portal._parent_student(parent, inactive_learner.id, db_session)
    assert inactive_link.value.status_code == 404
    with pytest.raises(HTTPException) as unverified_link:
        portal._parent_student(parent, unverified_learner.id, db_session)
    assert unverified_link.value.status_code == 404
    with pytest.raises(HTTPException) as cross_school_link:
        portal._parent_student(parent, other_school_learner.id, db_session)
    assert cross_school_link.value.status_code == 404
