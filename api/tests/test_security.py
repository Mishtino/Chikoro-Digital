from app.models.paynow import PaynowAttempt
from app.models.payment import Payment
from app.models.school import School
from app.models.student import Student
from app.models.user import User
from app.services.auth import create_access_token, hash_password
from app.services.crypto import encrypt


def _token(user):
    return create_access_token(str(user.id), user.school_id, user.role, user.is_admin)


def test_render_default_health_probe_returns_ok(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_endpoint_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_school_owner_cannot_create_global_admin(client, seed_two_schools):
    owner = seed_two_schools["u1"]
    response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {_token(owner)}"},
        json={
            "email": "attacker@example.com",
            "full_name": "Escalated User",
            "password": "a-strong-test-password",
            "role": "admin",
        },
    )
    assert response.status_code == 403


def test_teacher_cannot_record_financial_payment(client, db_session):
    school = School(code="PAY001", name="Payments School")
    db_session.add(school)
    db_session.flush()
    teacher = User(
        email="teacher@school.test",
        full_name="Teacher",
        password_hash=hash_password("test-password"),
        role="teacher",
        school_id=school.id,
    )
    db_session.add(teacher)
    db_session.commit()

    response = client.post(
        "/payments",
        headers={"Authorization": f"Bearer {_token(teacher)}"},
        json={"student_id": 1, "amount": 10, "school_id": school.id},
    )
    assert response.status_code == 403


def test_student_cannot_initiate_another_students_paynow_payment(client, db_session):
    school = School(
        code="PAY002",
        name="Portal School",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.flush()
    user = User(
        email="student1@school.test",
        full_name="Student One",
        password_hash=hash_password("test-password"),
        role="student",
        school_id=school.id,
    )
    db_session.add(user)
    db_session.flush()
    own_student = Student(
        school_id=school.id,
        student_number="PAY00200001",
        first_name="Student",
        last_name="One",
        portal_user_id=user.id,
    )
    other_student = Student(
        school_id=school.id,
        student_number="PAY00200002",
        first_name="Student",
        last_name="Two",
    )
    db_session.add_all([own_student, other_student])
    db_session.commit()

    response = client.post(
        "/paynow/initiate",
        headers={"Authorization": f"Bearer {_token(user)}"},
        json={"student_id": other_student.id, "amount": 10},
    )
    assert response.status_code == 403


def test_unsigned_paynow_paid_callback_does_not_create_payment(client, db_session, monkeypatch):
    from app.routers import paynow as paynow_router

    school = School(
        code="PAY003",
        name="Webhook School",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.flush()
    attempt = PaynowAttempt(
        school_id=school.id,
        reference="PN-UNSIGNED-TEST",
        amount=25,
        currency="USD",
        status="sent",
        poll_url="https://paynow.invalid/poll",
    )
    db_session.add(attempt)
    db_session.commit()

    monkeypatch.setattr(paynow_router, "verify_hash", lambda data, key: False)
    monkeypatch.setattr(
        paynow_router,
        "poll_transaction",
        lambda url, key: {"Status": "Paid", "hash_verified": False},
    )

    response = client.post(
        "/paynow/webhook",
        data={"reference": "PN-UNSIGNED-TEST", "status": "Paid"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "unverified"
    db_session.refresh(attempt)
    assert attempt.status == "sent"
    assert db_session.query(Payment).count() == 0


def test_student_cannot_read_another_students_report_card(client, db_session):
    school = School(code="RES001", name="Results School")
    db_session.add(school)
    db_session.flush()
    user = User(
        email="student@results.test",
        full_name="Student One",
        password_hash=hash_password("test-password"),
        role="student",
        school_id=school.id,
    )
    db_session.add(user)
    db_session.flush()
    own_student = Student(
        school_id=school.id,
        student_number="RES00100001",
        first_name="Student",
        last_name="One",
        portal_user_id=user.id,
    )
    other_student = Student(
        school_id=school.id,
        student_number="RES00100002",
        first_name="Student",
        last_name="Two",
    )
    db_session.add_all([own_student, other_student])
    db_session.commit()

    response = client.get(
        f"/results/report-card/{other_student.id}",
        headers={"Authorization": f"Bearer {_token(user)}"},
    )
    assert response.status_code == 403


def test_production_auth_uses_verified_supabase_identity_and_profile_role(client, db_session, monkeypatch):
    import uuid
    from types import SimpleNamespace

    from app import deps
    from app.config import settings
    from app.models.profile import Profile

    school = School(code="AUTH001", name="Auth School")
    db_session.add(school)
    db_session.flush()
    user = User(
        email="auth-user@example.test",
        full_name="Auth User",
        password_hash=hash_password("unused-password"),
        role="teacher",
        school_id=school.id,
    )
    db_session.add(user)
    db_session.flush()

    auth_user_id = str(uuid.uuid4())
    db_session.add(Profile(
        id=auth_user_id,
        local_user_id=user.id,
        role="owner",
        school_id=school.id,
        is_active=True,
    ))
    db_session.commit()

    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_publishable_key", "sb_publishable_test")
    monkeypatch.setattr(
        deps.httpx,
        "get",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200,
            json=lambda: {"id": auth_user_id, "email": user.email},
        ),
    )

    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer verified-supabase-access-token"},
    )

    assert response.status_code == 200
    assert response.json()["auth_user_id"] == auth_user_id
    assert response.json()["role"] == "owner"
    assert response.json()["is_admin"] is False


def test_production_auth_rejects_unverified_supabase_token(client, db_session, monkeypatch):
    from types import SimpleNamespace

    from app import deps
    from app.config import settings

    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_publishable_key", "sb_publishable_test")
    monkeypatch.setattr(
        deps.httpx,
        "get",
        lambda *args, **kwargs: SimpleNamespace(status_code=401, json=lambda: {}),
    )

    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401



def test_inactive_student_cannot_activate_portal_account(client, db_session):
    from app import deps
    from app.models.student import Student
    from app.services.ids import hash_pin

    school = School(code="ACT001", name="Activation School")
    db_session.add(school)
    db_session.flush()
    student = Student(
        school_id=school.id,
        student_number="ACT00100001",
        first_name="Inactive",
        last_name="Learner",
        status="inactive",
        activation_pin_hash=hash_pin("123456"),
    )
    db_session.add(student)
    db_session.commit()

    from app.main import app
    app.dependency_overrides[deps.get_supabase_auth_identity] = lambda: {
        "id": "00000000-0000-4000-8000-000000000001",
        "email": "learner@example.test",
        "email_confirmed_at": "2026-11-04T08:00:00Z",
    }

    response = client.post(
        "/portal/register",
        json={
            "school_code": "ACT001",
            "student_number": "ACT00100001",
            "pin": "123456",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only active learners can activate a portal account."
    db_session.refresh(student)
    assert student.portal_user_id is None
    assert student.activation_pin_hash is not None
