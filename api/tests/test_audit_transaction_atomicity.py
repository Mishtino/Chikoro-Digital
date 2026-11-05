"""Regression checks: audit insert failure must roll back the domain write."""
from datetime import time
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.audit import AuditLog
from app.models.class_assignment import ClassTeacherAssignment
from app.models.fee import Term
from app.models.results import Subject
from app.models.student import Student
from app.models.timetable import TimetableEntry
from app.models.user import User
from app.routers import classes, timetable
from app.services.auth import hash_password


def _owner_principal(owner, school):
    return SupabasePrincipal(
        auth_user_id=uuid4(), user_id=owner.id, school_id=school.id,
        role="owner", is_admin=False,
    )


def _reject_audit_at_commit(db, principal, action, entity_type=None, entity_id=None,
                            details=None, school_id=None):
    # A NOT NULL failure during the real transaction commit, rather than an
    # exception before the audit row is added, exercises database atomicity.
    db.add(AuditLog(
        school_id=school_id, actor_user_id=principal.user_id,
        action=None, entity_type=entity_type,
    ))
    db.commit()


def test_class_assignment_rolls_back_when_audit_insert_fails(
    client, db_session, seed_two_schools, monkeypatch
):
    school = seed_two_schools["s1"]
    owner = seed_two_schools["u1"]
    teacher = User(
        email="audit-class-teacher@example.com", full_name="Audit Teacher",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=school.id, is_active=True, is_admin=False,
    )
    student = Student(
        school_id=school.id, student_number="AUDIT-CLS-001",
        first_name="Audit", last_name="Learner", form="Form 1", status="active",
    )
    db_session.add_all([teacher, student])
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _owner_principal(owner, school)
    monkeypatch.setattr(classes, "write_audit", _reject_audit_at_commit)

    with pytest.raises(IntegrityError):
        client.post("/classes/assignments", json={
            "class_name": "Form 1", "teacher_user_id": teacher.id,
        })
    db_session.rollback()
    assert db_session.query(ClassTeacherAssignment).filter(
        ClassTeacherAssignment.school_id == school.id,
        ClassTeacherAssignment.teacher_user_id == teacher.id,
    ).count() == 0


def test_timetable_entry_rolls_back_when_audit_insert_fails(
    client, db_session, seed_two_schools, monkeypatch
):
    school = seed_two_schools["s1"]
    owner = seed_two_schools["u1"]
    term = Term(school_id=school.id, name="Audit Term", academic_year="2027")
    subject = Subject(school_id=school.id, name="Audit Science", code="AUD-SCI")
    db_session.add_all([term, subject])
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _owner_principal(owner, school)
    monkeypatch.setattr(timetable, "write_audit", _reject_audit_at_commit)

    with pytest.raises(IntegrityError):
        client.post("/timetable/entries", json={
            "term_id": term.id, "subject_id": subject.id,
            "class_name": "Form 1", "day_of_week": 1,
            "period_number": 1, "start_time": "08:00", "end_time": "08:40",
        })
    db_session.rollback()
    assert db_session.query(TimetableEntry).filter(
        TimetableEntry.school_id == school.id,
        TimetableEntry.class_name == "Form 1",
    ).count() == 0
