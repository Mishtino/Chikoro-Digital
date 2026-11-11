"""Classroom scheduling API tests. Uses synthetic schools and overridden identity."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.class_assignment import ClassTeacherAssignment
from app.models.classroom import ClassroomSettings
from app.models.student import Student
from app.models.user import User


def test_classroom_schedule_and_tenant_visibility(client, db_session, seed_two_schools):
    school1, school2 = seed_two_schools["s1"], seed_two_schools["s2"]
    teacher = User(email="vc-teacher@test.invalid", full_name="Teacher",
                   password_hash="unused", role="teacher", school_id=school1.id)
    learner = User(email="vc-student@test.invalid", full_name="Student",
                   password_hash="unused", role="student", school_id=school1.id)
    outsider = User(email="vc-outsider@test.invalid", full_name="Other",
                    password_hash="unused", role="student", school_id=school2.id)
    db_session.add_all([teacher, learner, outsider])
    db_session.flush()
    db_session.add_all([
        ClassTeacherAssignment(school_id=school1.id, class_name="Form 4A",
            teacher_user_id=teacher.id, assigned_by_user_id=seed_two_schools["u1"].id),
        Student(school_id=school1.id, student_number="VC-TEST-1",
            first_name="Learner", last_name="One", form="Form 4A",
            status="active", portal_user_id=learner.id),
        ClassroomSettings(school_id=school1.id, embedded_enabled=True),
    ])
    db_session.commit()

    current = [teacher]
    def authenticated():
        u = current[0]
        return SupabasePrincipal(UUID(int=u.id), u.id, u.school_id, u.role, bool(u.is_admin))
    app.dependency_overrides[get_supabase_principal] = authenticated
    try:
        now = datetime.now(timezone.utc) + timedelta(days=1)
        payload = {"class_name":"Form 4A", "mode":"embedded", "provider":"jitsi",
            "starts_at":now.isoformat(), "ends_at":(now + timedelta(hours=1)).isoformat()}
        created = client.post("/classrooms", json=payload)
        assert created.status_code == 201, created.text
        assert len(client.get("/classrooms").json()) == 1

        current[0] = learner
        assert len(client.get("/classrooms").json()) == 1
        assert client.post("/classrooms", json=payload).status_code == 403

        current[0] = outsider
        assert client.get("/classrooms").json() == []
        assert client.post("/classrooms", json=payload).status_code == 403

        current[0] = teacher
        payload["mode"] = "external"
        payload["provider"] = "zoom"
        assert client.post("/classrooms", json=payload).status_code == 403
    finally:
        app.dependency_overrides.pop(get_supabase_principal, None)
