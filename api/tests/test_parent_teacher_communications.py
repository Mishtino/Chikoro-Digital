from uuid import uuid4

from sqlalchemy import text

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.class_assignment import ClassTeacherAssignment
from app.models.parent_teacher_message import ParentTeacherConversation
from app.models.student import Contact, Student
from app.models.user import User
from app.services.auth import hash_password


def principal(user, school, role=None, auth_user_id=None):
    return SupabasePrincipal(
        auth_user_id=auth_user_id or uuid4(), user_id=user.id, school_id=school.id,
        role=role or user.role, is_admin=False,
    )


def _attach_verified_guardian_link(db_session, school, learner, profile_id):
    """Exercise the same attached public-schema guardian query used in production."""
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
    contact = Contact(
        school_id=school.id, student_id=learner.id,
        name="Verified guardian", relationship="parent", is_primary=True,
    )
    db_session.add(contact)
    db_session.flush()
    # The attached schema is a SQLite mirror, so keep its contact row in sync
    # with the contact created above before exercising the production query.
    db_session.execute(text("""
        INSERT INTO public.contacts (id, school_id, student_id)
        VALUES (:contact_id, :school_id, :student_id)
    """), {
        "contact_id": contact.id,
        "school_id": school.id,
        "student_id": learner.id,
    })
    db_session.execute(text("""
        INSERT INTO public.guardian_links
            (profile_id, contact_id, school_id, is_active, verified_at)
        VALUES (:profile_id, :contact_id, :school_id, true, '2026-11-05T10:00:00Z')
    """), {
        "profile_id": str(profile_id),
        "contact_id": contact.id,
        "school_id": school.id,
    })
    db_session.commit()


def test_parent_teacher_messages_are_scoped_to_verified_child_and_assigned_teacher(
    client, db_session, seed_two_schools
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
    db_session.flush()
    profile_id = uuid4()
    _attach_verified_guardian_link(db_session, school, learner, profile_id)
    app.dependency_overrides[get_supabase_principal] = lambda: principal(
        parent, school, auth_user_id=profile_id
    )

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

    # The inbox and message routes must resolve the real verified guardian link.
    parent_inbox = client.get("/communications/conversations")
    assert parent_inbox.status_code == 200
    assert [row["id"] for row in parent_inbox.json()["conversations"]] == [conversation_id]

    sent = client.post(
        f"/communications/conversations/{conversation_id}/messages",
        json={"body": "Could you please explain the homework task?"},
    )
    assert sent.status_code == 201
    assert sent.json()["is_mine"] is True

    # Revoking the verified link must immediately remove inbox and message access.
    db_session.execute(text(
        "UPDATE public.guardian_links SET is_active = false WHERE profile_id = :profile_id"
    ), {"profile_id": str(profile_id)})
    db_session.commit()
    revoked_link_inbox = client.get("/communications/conversations")
    assert revoked_link_inbox.status_code == 200
    assert revoked_link_inbox.json()["conversations"] == []
    revoked_message = client.post(
        f"/communications/conversations/{conversation_id}/messages",
        json={"body": "This should no longer be allowed"},
    )
    assert revoked_message.status_code == 404

    # Restore the verified relationship for the teacher-side checks below.
    db_session.execute(text(
        "UPDATE public.guardian_links SET is_active = true WHERE profile_id = :profile_id"
    ), {"profile_id": str(profile_id)})
    db_session.commit()

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
    client, db_session, seed_two_schools
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
    db_session.flush()
    profile_id = uuid4()
    _attach_verified_guardian_link(db_session, school, learner, profile_id)
    app.dependency_overrides[get_supabase_principal] = lambda: principal(
        parent, school, auth_user_id=profile_id
    )

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
