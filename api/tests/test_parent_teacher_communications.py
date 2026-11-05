from uuid import uuid4

from fastapi import HTTPException

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.class_assignment import ClassTeacherAssignment
from app.models.parent_teacher_message import ParentTeacherConversation
from app.models.student import Student
from app.models.user import User
from app.routers import parent_teacher
from app.services.auth import hash_password


def principal(user, school, role=None):
    return SupabasePrincipal(
        auth_user_id=uuid4(), user_id=user.id, school_id=school.id,
        role=role or user.role, is_admin=False,
    )


def test_parent_teacher_messages_are_scoped_to_verified_child_and_assigned_teacher(
    client, db_session, seed_two_schools, monkeypatch
):
    school = seed_two_schools["s1"]
    parent = User(
        email="parent.message@example.com", full_name="Parent Account",
        password_hash=hash_password("test-password"), role="parent",
        school_id=school.id, is_active=True, is_admin=False,
    )
    teacher = User(
        email="teacher.message@example.com", full_name="Assigned Teacher",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=school.id, is_active=True, is_admin=False,
    )
    other_teacher = User(
        email="teacher.other@example.com", full_name="Other Teacher",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=school.id, is_active=True, is_admin=False,
    )
    learner = Student(
        school_id=school.id, student_number="MSG-001",
        first_name="Tariro", last_name="Moyo", form="Form 1", status="active",
    )
    db_session.add_all([parent, teacher, other_teacher, learner])
    db_session.flush()
    db_session.add(ClassTeacherAssignment(
        school_id=school.id, class_name="Form 1",
        teacher_user_id=teacher.id, assigned_by_user_id=seed_two_schools["u1"].id,
        is_active=True,
    ))
    db_session.commit()

    monkeypatch.setattr(parent_teacher, "_parent_student", lambda _principal, sid, _db: (
        learner if sid == learner.id else (_ for _ in ()).throw(
            HTTPException(status_code=404, detail="Linked student not found")
        )
    ))
    app.dependency_overrides[get_supabase_principal] = lambda: principal(parent, school)

    created = client.post("/communications/conversations", json={
        "student_id": learner.id, "teacher_user_id": teacher.id,
        "subject": "Homework support",
    })
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    rejected = client.post("/communications/conversations", json={
        "student_id": learner.id, "teacher_user_id": other_teacher.id,
        "subject": "Private discussion",
    })
    assert rejected.status_code == 404

    # The parent inbox must re-check current verified guardian links rather
    # than exposing conversations solely because a thread exists.
    monkeypatch.setattr(parent_teacher, "_parent_student_ids", lambda _principal, _db: [learner.id])
    parent_inbox = client.get("/communications/conversations")
    assert parent_inbox.status_code == 200
    assert [row["id"] for row in parent_inbox.json()["conversations"]] == [conversation_id]
    monkeypatch.setattr(parent_teacher, "_parent_student_ids", lambda _principal, _db: [])
    revoked_link_inbox = client.get("/communications/conversations")
    assert revoked_link_inbox.status_code == 200
    assert revoked_link_inbox.json()["conversations"] == []

    sent = client.post(
        f"/communications/conversations/{conversation_id}/messages",
        json={"body": "Could you please explain the homework task?"},
    )
    assert sent.status_code == 201
    assert sent.json()["is_mine"] is True

    app.dependency_overrides[get_supabase_principal] = lambda: principal(teacher, school)
    inbox = client.get("/communications/conversations")
    assert inbox.status_code == 200
    assert [row["id"] for row in inbox.json()["conversations"]] == [conversation_id]

    messages = client.get(f"/communications/conversations/{conversation_id}/messages")
    assert messages.status_code == 200
    assert messages.json()["messages"][0]["body"] == "Could you please explain the homework task?"

    reply = client.post(
        f"/communications/conversations/{conversation_id}/messages",
        json={"body": "I will share the clarification with the class."},
    )
    assert reply.status_code == 201

    app.dependency_overrides[get_supabase_principal] = lambda: principal(other_teacher, school)
    assert client.get(f"/communications/conversations/{conversation_id}/messages").status_code == 404
    assert client.post(
        f"/communications/conversations/{conversation_id}/messages",
        json={"body": "Unauthorized reply"},
    ).status_code == 404


def test_parent_teacher_conversation_rejects_empty_message_and_closed_thread(
    client, db_session, seed_two_schools, monkeypatch
):
    school = seed_two_schools["s1"]
    parent = User(
        email="parent.closed@example.com", full_name="Parent",
        password_hash=hash_password("test-password"), role="parent",
        school_id=school.id, is_active=True, is_admin=False,
    )
    teacher = User(
        email="teacher.closed@example.com", full_name="Teacher",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=school.id, is_active=True, is_admin=False,
    )
    learner = Student(
        school_id=school.id, student_number="MSG-002",
        first_name="Rudo", last_name="Moyo", form="Form 2", status="active",
    )
    db_session.add_all([parent, teacher, learner])
    db_session.flush()
    conversation = ParentTeacherConversation(
        school_id=school.id, student_id=learner.id, parent_user_id=parent.id,
        teacher_user_id=teacher.id, subject="Attendance", status="closed",
    )
    db_session.add(conversation)
    db_session.commit()

    monkeypatch.setattr(parent_teacher, "_parent_student", lambda _principal, sid, _db: learner)
    app.dependency_overrides[get_supabase_principal] = lambda: principal(parent, school)

    empty = client.post(
        f"/communications/conversations/{conversation.id}/messages",
        json={"body": "   "},
    )
    assert empty.status_code == 422

    closed = client.post(
        f"/communications/conversations/{conversation.id}/messages",
        json={"body": "A follow-up"},
    )
    assert closed.status_code == 409
