from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.paynow import PaynowAttempt
from app.models.payment import Invoice, Payment, PaymentAllocation, Receipt
from app.models.school import School
from app.models.student import Student
from app.models.user import User
from app.routers import paynow
from app.services.crypto import encrypt


def _student_principal(user_id, school_id, auth_user_id=None):
    return SupabasePrincipal(
        auth_user_id=auth_user_id or uuid4(),
        user_id=user_id,
        school_id=school_id,
        role="student",
        is_admin=False,
    )


def test_student_cannot_initiate_paynow_for_another_learner(client, db_session):
    school = School(code="PN001", name="Paynow School")
    db_session.add(school)
    db_session.flush()
    own_user = User(
        email="student-one@example.test", full_name="Student One",
        password_hash="unused", role="student", school_id=school.id,
    )
    other_user = User(
        email="student-two@example.test", full_name="Student Two",
        password_hash="unused", role="student", school_id=school.id,
    )
    db_session.add_all([own_user, other_user])
    db_session.flush()
    own_student = Student(
        school_id=school.id, student_number="PN-S1", first_name="One",
        last_name="Learner", status="active", portal_user_id=own_user.id,
    )
    other_student = Student(
        school_id=school.id, student_number="PN-S2", first_name="Two",
        last_name="Learner", status="active", portal_user_id=other_user.id,
    )
    db_session.add_all([own_student, other_student])
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _student_principal(
        own_user.id, school.id
    )
    response = client.post(
        "/paynow/initiate",
        json={"student_id": other_student.id, "amount": 1, "school_id": school.id},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied"
    assert db_session.query(PaynowAttempt).count() == 0


def test_duplicate_paid_paynow_webhooks_create_one_payment_allocation_and_receipt(
    client, db_session, monkeypatch
):
    school = School(
        code="PN002", name="Paynow Webhook School",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.flush()
    user = User(
        email="webhook-student@example.test", full_name="Webhook Student",
        password_hash="unused", role="student", school_id=school.id,
    )
    db_session.add(user)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PN-W1", first_name="Webhook",
        last_name="Student", status="active", portal_user_id=user.id,
    )
    db_session.add(student)
    db_session.flush()
    invoice = Invoice(
        school_id=school.id, student_id=student.id, invoice_number="PN-INV-1",
        currency="USD", total=25, status="issued",
    )
    db_session.add(invoice)
    db_session.flush()
    attempt = PaynowAttempt(
        school_id=school.id, student_id=student.id, invoice_id=invoice.id,
        reference="PN-DUPLICATE-1", amount=25, currency="USD",
        status="sent", poll_url="https://paynow.example.test/poll/1",
    )
    db_session.add(attempt)
    db_session.commit()

    monkeypatch.setattr(
        paynow, "poll_transaction",
        lambda _url, _key: {"Status": "Paid", "hash_verified": True},
    )

    first = client.post("/paynow/webhook", data={"reference": attempt.reference})
    second = client.post("/paynow/webhook", data={"reference": attempt.reference})

    assert first.status_code == 200
    assert second.status_code == 200
    assert db_session.query(Payment).filter(
        Payment.reference == f"paynow:{attempt.id}"
    ).count() == 1
    payment = db_session.query(Payment).filter(
        Payment.reference == f"paynow:{attempt.id}"
    ).one()
    assert db_session.query(PaymentAllocation).filter(
        PaymentAllocation.payment_id == payment.id
    ).count() == 1
    assert db_session.query(Receipt).filter(
        Receipt.payment_id == payment.id
    ).count() == 1
    assert db_session.query(PaynowAttempt).filter(
        PaynowAttempt.id == attempt.id, PaynowAttempt.status == "paid"
    ).count() == 1


def test_unverified_paid_paynow_webhook_does_not_create_financial_records(
    client, db_session, monkeypatch
):
    school = School(
        code="PN003", name="Unverified Paynow School",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.flush()
    user = User(
        email="unverified-student@example.test", full_name="Unverified Student",
        password_hash="unused", role="student", school_id=school.id,
    )
    db_session.add(user)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PN-U1", first_name="Unverified",
        last_name="Student", status="active", portal_user_id=user.id,
    )
    db_session.add(student)
    db_session.flush()
    attempt = PaynowAttempt(
        school_id=school.id, student_id=student.id, reference="PN-UNVERIFIED-1",
        amount=10, currency="USD", status="sent",
        poll_url="https://paynow.example.test/poll/unverified",
    )
    db_session.add(attempt)
    db_session.commit()

    monkeypatch.setattr(
        paynow, "poll_transaction",
        lambda _url, _key: {"Status": "Paid", "hash_verified": False},
    )
    response = client.post("/paynow/webhook", data={"reference": attempt.reference})

    assert response.status_code == 200
    assert response.json()["status"] == "payment confirmation hash could not be verified"
    assert db_session.query(Payment).count() == 0
    assert db_session.query(PaymentAllocation).count() == 0
    assert db_session.query(Receipt).count() == 0
    db_session.refresh(attempt)
    assert attempt.status == "unverified"
