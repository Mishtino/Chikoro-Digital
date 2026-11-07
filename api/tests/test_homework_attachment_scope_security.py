from uuid import uuid4

from sqlalchemy import text


def _prepare_guardian_link_schema(db_session):
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


from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.class_assignment import ClassTeacherAssignment
from app.models.homework import HomeworkAssignment, HomeworkAttachment, HomeworkSubmission
from app.models.results import Subject
from app.models.student import Student
from app.models.user import User
from app.services.auth import hash_password


def _principal(user, school):
    return SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=user.id,
        school_id=school.id,
        role=user.role,
        is_admin=False,
    )


def test_assigned_teacher_cannot_read_another_teachers_submission_attachments(
    client, db_session, seed_two_schools, monkeypatch
):
    from app.routers import homework as homework_router

    monkeypatch.setattr(homework_router.settings, "homework_attachments_enabled", True)
    school = seed_two_schools["s1"]
    creator = User(
        email="homework.creator.scope@example.com",
        full_name="Assignment Creator",
        password_hash=hash_password("test-password"),
        role="teacher",
        school_id=school.id,
        is_active=True,
        is_admin=False,
    )
    other_teacher = User(
        email="homework.other.scope@example.com",
        full_name="Other Teacher",
        password_hash=hash_password("test-password"),
        role="teacher",
        school_id=school.id,
        is_active=True,
        is_admin=False,
    )
    learner = Student(
        school_id=school.id,
        student_number="HW-SCOPE-001",
        first_name="Tariro",
        last_name="Moyo",
        form="Form 1",
        status="active",
    )
    subject = Subject(school_id=school.id, name="English", code="HW-SCOPE-ENG")
    db_session.add_all([creator, other_teacher, learner, subject])
    db_session.flush()

    assignment = HomeworkAssignment(
        school_id=school.id,
        class_name="Form 1",
        subject_id=subject.id,
        title="Private essay",
        instructions="Submit your essay.",
        status="published",
        created_by_user_id=creator.id,
    )
    db_session.add(assignment)
    db_session.flush()
    submission = HomeworkSubmission(
        school_id=school.id,
        assignment_id=assignment.id,
        student_id=learner.id,
        answer_text="My essay.",
    )
    db_session.add(submission)
    db_session.flush()
    attachment = HomeworkAttachment(
        school_id=school.id,
        submission_id=submission.id,
        uploaded_by_user_id=creator.id,
        object_path=f"schools/{school.id}/private-test.pdf",
        original_filename="private-test.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        status="ready",
    )
    db_session.add_all([
        attachment,
        ClassTeacherAssignment(
            school_id=school.id,
            class_name="Form 1",
            teacher_user_id=other_teacher.id,
            assigned_by_user_id=seed_two_schools["u1"].id,
            is_active=True,
        ),
    ])
    db_session.commit()

    download_calls = []
    monkeypatch.setattr(
        homework_router,
        "create_download_url",
        lambda *args, **kwargs: download_calls.append(args) or "https://storage.example/private",
    )
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(other_teacher, school)

    listed = client.get(f"/homework/submissions/{submission.id}/attachments")
    assert listed.status_code == 404

    downloaded = client.post(f"/homework/attachments/{attachment.id}/download-url")
    assert downloaded.status_code == 404
    assert download_calls == []


def test_parent_cannot_read_or_download_an_unlinked_child_attachment(
    client, db_session, seed_two_schools, monkeypatch
):
    from fastapi import HTTPException
    from app.routers import homework as homework_router

    monkeypatch.setattr(homework_router.settings, "homework_attachments_enabled", True)
    school = seed_two_schools["s1"]
    owner = seed_two_schools["u1"]
    linked_learner = Student(
        school_id=school.id, student_number="HW-PARENT-LINKED",
        first_name="Rudo", last_name="Moyo", form="Form 1", status="active",
    )
    unlinked_learner = Student(
        school_id=school.id, student_number="HW-PARENT-OTHER",
        first_name="Tariro", last_name="Dube", form="Form 1", status="active",
    )
    subject = Subject(school_id=school.id, name="Parent Homework", code="HW-PARENT-ENG")
    db_session.add_all([linked_learner, unlinked_learner, subject])
    db_session.flush()
    assignment = HomeworkAssignment(
        school_id=school.id, class_name="Form 1", subject_id=subject.id,
        title="Parent visibility check", instructions="Read only.",
        status="published", created_by_user_id=owner.id,
    )
    db_session.add(assignment)
    db_session.flush()
    submission = HomeworkSubmission(
        school_id=school.id, assignment_id=assignment.id,
        student_id=unlinked_learner.id, answer_text="Private response",
    )
    db_session.add(submission)
    db_session.flush()
    attachment = HomeworkAttachment(
        school_id=school.id, submission_id=submission.id,
        uploaded_by_user_id=owner.id,
        object_path=f"schools/{school.id}/parent-private.pdf",
        original_filename="parent-private.pdf", content_type="application/pdf",
        size_bytes=512, status="ready",
    )
    db_session.add(attachment)
    db_session.commit()

    from app.models.student import Contact

    guardian_contact = Contact(
        school_id=school.id, student_id=linked_learner.id,
        name="Verified guardian", relationship="parent", is_primary=True,
    )
    db_session.add(guardian_contact)
    db_session.flush()
    profile_id = uuid4()
    _prepare_guardian_link_schema(db_session)
    db_session.execute(text("""
        INSERT INTO public.guardian_links
            (profile_id, contact_id, school_id, is_active, verified_at)
        VALUES (:profile_id, :contact_id, :school_id, true, '2026-11-05T10:00:00Z')
    """), {
        "profile_id": str(profile_id),
        "contact_id": guardian_contact.id,
        "school_id": school.id,
    })
    db_session.commit()

    # Exercise the real guardian-link SQL through the homework routes. The
    # linked sibling is authorized; the unlinked sibling must remain hidden.
    parent = SupabasePrincipal(
        auth_user_id=profile_id, user_id=9901, school_id=school.id,
        role="parent", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: parent
    download_calls = []
    monkeypatch.setattr(
        homework_router, "create_download_url",
        lambda *args, **kwargs: download_calls.append(args) or "https://storage.example/private",
    )

    assignments = client.get(
        f"/homework/parent/children/{unlinked_learner.id}/assignments"
    )
    assert assignments.status_code == 404

    listed = client.get(f"/homework/submissions/{submission.id}/attachments")
    assert listed.status_code == 404

    downloaded = client.post(
        f"/homework/attachments/{attachment.id}/download-url"
    )
    assert downloaded.status_code == 404
    assert download_calls == []
