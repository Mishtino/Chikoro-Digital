from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.class_assignment import ClassTeacherAssignment
from app.models.homework import HomeworkAssignment
from app.models.results import Subject
from app.models.student import Student
from app.models.user import User
from app.services.auth import hash_password


def _principal(user, school):
    return SupabasePrincipal(
        auth_user_id=uuid4(), user_id=user.id, school_id=school.id,
        role=user.role, is_admin=False,
    )


def test_homework_teacher_student_submission_and_marking(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    teacher = User(
        email="homework.teacher@example.com", full_name="Homework Teacher",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=school.id, is_active=True, is_admin=False,
    )
    learner_user = User(
        email="homework.student@example.com", full_name="Learner",
        password_hash=hash_password("test-password"), role="student",
        school_id=school.id, is_active=True, is_admin=False,
    )
    student = Student(
        school_id=school.id, student_number="HW-001", first_name="Tariro",
        last_name="Moyo", form="Form 1", status="active",
    )
    subject = Subject(school_id=school.id, name="Mathematics", code="MATH")
    db_session.add_all([teacher, learner_user, student, subject])
    db_session.flush()
    student.portal_user_id = learner_user.id
    db_session.add(ClassTeacherAssignment(
        school_id=school.id, class_name="Form 1", teacher_user_id=teacher.id,
        assigned_by_user_id=seed_two_schools["u1"].id, is_active=True,
    ))
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _principal(teacher, school)
    created = client.post("/homework/assignments", json={
        "class_name": "Form 1", "subject_id": subject.id,
        "title": "Fractions practice", "instructions": "Complete questions 1 to 10.",
        "publish": True,
    })
    assert created.status_code == 201
    assignment_id = created.json()["id"]

    app.dependency_overrides[get_supabase_principal] = lambda: _principal(learner_user, school)
    available = client.get("/homework/student/assignments")
    assert available.status_code == 200
    assert available.json()["assignments"][0]["submission_status"] == "not_submitted"

    submitted = client.post(
        f"/homework/student/assignments/{assignment_id}/submit",
        json={"answer_text": "My completed answers are 1 to 10."},
    )
    assert submitted.status_code == 201
    duplicate = client.post(
        f"/homework/student/assignments/{assignment_id}/submit",
        json={"answer_text": "Second attempt"},
    )
    assert duplicate.status_code == 409

    app.dependency_overrides[get_supabase_principal] = lambda: _principal(teacher, school)
    submissions = client.get(f"/homework/assignments/{assignment_id}/submissions")
    assert submissions.status_code == 200
    assert submissions.json()["submissions"][0]["student_id"] == student.id
    marked = client.post(
        f"/homework/submissions/{submitted.json()['id']}/mark",
        json={"feedback": "Good effort.", "score": 8},
    )
    assert marked.status_code == 200
    assert marked.json()["status"] == "marked"


def test_homework_teacher_cannot_create_for_unassigned_class(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    teacher = User(
        email="homework.unassigned@example.com", full_name="Unassigned Teacher",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=school.id, is_active=True, is_admin=False,
    )
    subject = Subject(school_id=school.id, name="English", code="ENG")
    db_session.add_all([teacher, subject])
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(teacher, school)

    response = client.post("/homework/assignments", json={
        "class_name": "Form 4", "subject_id": subject.id,
        "title": "Essay", "instructions": "Write an essay.",
    })
    assert response.status_code == 403


def test_homework_assignment_is_school_scoped(client, db_session, seed_two_schools):
    school = seed_two_schools["s1"]
    teacher = User(
        email="homework.scope@example.com", full_name="Scoped Teacher",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=school.id, is_active=True, is_admin=False,
    )
    subject = Subject(school_id=school.id, name="Science", code="SCI")
    db_session.add_all([teacher, subject])
    db_session.flush()
    db_session.add(ClassTeacherAssignment(
        school_id=school.id, class_name="Form 2", teacher_user_id=teacher.id,
        assigned_by_user_id=seed_two_schools["u1"].id, is_active=True,
    ))
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(teacher, school)

    response = client.post("/homework/assignments", json={
        "class_name": "Form 2", "subject_id": subject.id,
        "title": "Lab report", "instructions": "Describe the experiment.",
    })
    assert response.status_code == 201


def test_homework_private_attachment_upload_completion_and_download(
    client, db_session, seed_two_schools, monkeypatch
):
    from app.routers import homework as homework_router
    monkeypatch.setattr(homework_router.settings, "homework_attachments_enabled", True)

    school = seed_two_schools["s1"]
    teacher = User(
        email="attachment.teacher@example.com", full_name="Attachment Teacher",
        password_hash=hash_password("test-password"), role="teacher",
        school_id=school.id, is_active=True, is_admin=False,
    )
    learner_user = User(
        email="attachment.student@example.com", full_name="Attachment Learner",
        password_hash=hash_password("test-password"), role="student",
        school_id=school.id, is_active=True, is_admin=False,
    )
    student = Student(
        school_id=school.id, student_number="ATT-001", first_name="Tariro",
        last_name="Moyo", form="Form 1", status="active",
    )
    subject = Subject(school_id=school.id, name="English", code="ATT-ENG")
    db_session.add_all([teacher, learner_user, student, subject])
    db_session.flush()
    student.portal_user_id = learner_user.id
    db_session.add(ClassTeacherAssignment(
        school_id=school.id, class_name="Form 1", teacher_user_id=teacher.id,
        assigned_by_user_id=seed_two_schools["u1"].id, is_active=True,
    ))
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _principal(teacher, school)
    created = client.post("/homework/assignments", json={
        "class_name": "Form 1", "subject_id": subject.id,
        "title": "Essay upload", "instructions": "Write and upload an essay.",
        "publish": True,
    })
    assert created.status_code == 201

    app.dependency_overrides[get_supabase_principal] = lambda: _principal(learner_user, school)
    submitted = client.post(
        f"/homework/student/assignments/{created.json()['id']}/submit",
        json={"answer_text": "Please see my attached essay."},
    )
    assert submitted.status_code == 201
    submission_id = submitted.json()["id"]

    monkeypatch.setattr(homework_router, "create_upload_url", lambda path: "https://storage.example/upload-token")
    upload = client.post(
        f"/homework/student/submissions/{submission_id}/attachments/upload-url",
        json={
            "filename": "../../my-essay.pdf",
            "content_type": "application/pdf",
            "size_bytes": 4096,
        },
    )
    assert upload.status_code == 201
    assert upload.json()["upload_url"] == "https://storage.example/upload-token"
    assert upload.json()["attachment"]["filename"] == "my-essay.pdf"
    attachment_id = upload.json()["attachment"]["id"]

    monkeypatch.setattr(
        homework_router, "inspect_object",
        lambda path: {"size_bytes": 4096, "content_type": "application/pdf"},
    )
    completed = client.post(f"/homework/student/attachments/{attachment_id}/complete")
    assert completed.status_code == 200
    assert completed.json()["status"] == "ready"

    listed = client.get(f"/homework/submissions/{submission_id}/attachments")
    assert listed.status_code == 200
    assert len(listed.json()["attachments"]) == 1

    monkeypatch.setattr(
        homework_router, "create_download_url",
        lambda path, expires_in=300: "https://storage.example/download-token",
    )
    downloaded = client.post(f"/homework/attachments/{attachment_id}/download-url")
    assert downloaded.status_code == 200
    assert downloaded.json()["download_url"] == "https://storage.example/download-token"
    assert downloaded.json()["expires_in_seconds"] == 300

    second_upload = client.post(
        f"/homework/student/submissions/{submission_id}/attachments/upload-url",
        json={
            "filename": "mismatch.pdf",
            "content_type": "application/pdf",
            "size_bytes": 1024,
        },
    )
    assert second_upload.status_code == 201
    monkeypatch.setattr(
        homework_router, "inspect_object",
        lambda path: {"size_bytes": 2048, "content_type": "application/pdf"},
    )
    mismatch = client.post(
        f"/homework/student/attachments/{second_upload.json()['attachment']['id']}/complete"
    )
    assert mismatch.status_code == 422

    other_user = User(
        email="attachment.other@example.com", full_name="Other Learner",
        password_hash=hash_password("test-password"), role="student",
        school_id=school.id, is_active=True, is_admin=False,
    )
    other_student = Student(
        school_id=school.id, student_number="ATT-OTHER", first_name="Other",
        last_name="Learner", form="Form 1", status="active",
    )
    db_session.add_all([other_user, other_student])
    db_session.flush()
    other_student.portal_user_id = other_user.id
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(other_user, school)
    denied = client.get(f"/homework/submissions/{submission_id}/attachments")
    assert denied.status_code == 404
    denied_download = client.post(f"/homework/attachments/{attachment_id}/download-url")
    assert denied_download.status_code == 404


def test_homework_attachment_rejects_disallowed_type(client, db_session, seed_two_schools, monkeypatch):
    from app.routers import homework as homework_router
    monkeypatch.setattr(homework_router.settings, "homework_attachments_enabled", True)
    school = seed_two_schools["s1"]
    learner_user = User(
        email="attachment.badtype@example.com", full_name="Learner",
        password_hash=hash_password("test-password"), role="student",
        school_id=school.id, is_active=True, is_admin=False,
    )
    student = Student(
        school_id=school.id, student_number="ATT-002", first_name="Tariro",
        last_name="Moyo", form="Form 1", status="active", portal_user_id=None,
    )
    db_session.add_all([learner_user, student])
    db_session.flush()
    student.portal_user_id = learner_user.id
    subject = Subject(school_id=school.id, name="Science", code="ATT-SCI")
    db_session.add(subject)
    db_session.flush()
    assignment = HomeworkAssignment(
        school_id=school.id, class_name="Form 1", subject_id=subject.id,
        title="Allowed upload", instructions="Upload a PDF.", status="published",
        created_by_user_id=seed_two_schools["u1"].id,
    )
    db_session.add(assignment)
    db_session.flush()
    from app.models.homework import HomeworkSubmission
    submission = HomeworkSubmission(
        school_id=school.id, assignment_id=assignment.id, student_id=student.id,
        answer_text="My answer",
    )
    db_session.add(submission)
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _principal(learner_user, school)
    response = client.post(
        f"/homework/student/submissions/{submission.id}/attachments/upload-url",
        json={"filename": "script.exe", "content_type": "application/octet-stream", "size_bytes": 100},
    )
    assert response.status_code == 415
