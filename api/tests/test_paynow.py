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
        lambda _url, _key: {"Status": "Paid", "reference": "PN-DUPLICATE-1", "amount": "25.00", "hash_verified": True},
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



def test_parent_cannot_initiate_paynow_for_unlinked_learner(
    client, db_session, monkeypatch
):
    school = School(code="PN004", name="Parent Isolation School")
    db_session.add(school)
    db_session.flush()
    learner = Student(
        school_id=school.id, student_number="PN-P1", first_name="Parent",
        last_name="Isolation", status="active",
    )
    db_session.add(learner)
    db_session.commit()

    parent = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=9004, school_id=school.id,
        role="parent", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: parent
    learner_id = learner.id
    original_execute = db_session.execute

    class EmptyLinkResult:
        @staticmethod
        def first():
            return None

    def execute_without_parent_link(statement, *args, **kwargs):
        if "guardian_links" in str(statement):
            return EmptyLinkResult()
        return original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", execute_without_parent_link)

    response = client.post(
        "/paynow/initiate",
        json={"student_id": learner_id, "amount": 1, "school_id": school.id},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Linked student not found"
    assert db_session.query(PaynowAttempt).count() == 0


def test_reconcile_paid_attempt_creates_one_payment_and_receipt(
    client, db_session, monkeypatch
):
    from app.services import paynow as paynow_service

    school = School(
        code="PN005", name="Reconciliation School",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.flush()
    user = User(
        email="reconcile-student@example.test", full_name="Reconcile Student",
        password_hash="unused", role="student", school_id=school.id,
    )
    db_session.add(user)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PN-R1", first_name="Reconcile",
        last_name="Student", status="active", portal_user_id=user.id,
    )
    db_session.add(student)
    db_session.flush()
    invoice = Invoice(
        school_id=school.id, student_id=student.id, invoice_number="PN-INV-R1",
        currency="USD", total=30, status="issued",
    )
    db_session.add(invoice)
    db_session.flush()
    attempt = PaynowAttempt(
        school_id=school.id, student_id=student.id, invoice_id=invoice.id,
        reference="PN-RECONCILE-1", amount=30, currency="USD",
        status="sent", poll_url="https://paynow.example.test/poll/reconcile",
    )
    db_session.add(attempt)
    db_session.commit()
    attempt_id = attempt.id

    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=1, school_id=None,
        role="vortex_admin", is_admin=True,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal
    monkeypatch.setattr(
        paynow_service, "poll_transaction",
        lambda _url, _key: {"Status": "Paid", "reference": "PN-RECONCILE-1", "amount": "30.00", "hash_verified": True},
    )

    first = client.post("/paynow/reconcile")
    second = client.post("/paynow/reconcile")

    assert first.status_code == 200
    assert first.json() == {"updated": 1}
    assert second.status_code == 200
    assert second.json() == {"updated": 0}
    payment = db_session.query(Payment).filter(
        Payment.reference == f"paynow:{attempt_id}"
    ).one()
    assert db_session.query(PaymentAllocation).filter(
        PaymentAllocation.payment_id == payment.id
    ).count() == 1
    assert db_session.query(Receipt).filter(
        Receipt.payment_id == payment.id
    ).count() == 1
    db_session.refresh(attempt)
    assert attempt.status == "paid"


def test_reconcile_retries_unverified_attempt_until_hash_is_verified(
    client, db_session, monkeypatch
):
    from app.services import paynow as paynow_service

    school = School(
        code="PN006", name="Retry Verification School",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.flush()
    user = User(
        email="retry-student@example.test", full_name="Retry Student",
        password_hash="unused", role="student", school_id=school.id,
    )
    db_session.add(user)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PN-R2", first_name="Retry",
        last_name="Student", status="active", portal_user_id=user.id,
    )
    db_session.add(student)
    db_session.flush()
    invoice = Invoice(
        school_id=school.id, student_id=student.id,
        invoice_number="PN-RETRY-INV", currency="USD", total=15,
        status="issued",
    )
    db_session.add(invoice)
    db_session.flush()
    attempt = PaynowAttempt(
        school_id=school.id, student_id=student.id, invoice_id=invoice.id,
        reference="PN-RETRY-1",
        amount=15, currency="USD", status="sent",
        poll_url="https://paynow.example.test/poll/retry",
    )
    db_session.add(attempt)
    db_session.commit()
    attempt_id = attempt.id

    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=1, school_id=None,
        role="vortex_admin", is_admin=True,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal
    poll_results = iter([
        {"Status": "Paid", "reference": "PN-RETRY-1", "amount": "15.00", "hash_verified": False},
        {"Status": "Paid", "reference": "PN-RETRY-1", "amount": "15.00", "hash_verified": True},
    ])
    monkeypatch.setattr(
        paynow_service, "poll_transaction",
        lambda _url, _key: next(poll_results),
    )

    first = client.post("/paynow/reconcile")
    db_session.refresh(attempt)
    assert first.status_code == 200
    assert first.json() == {"updated": 1}
    assert attempt.status == "unverified"
    assert db_session.query(Payment).count() == 0

    second = client.post("/paynow/reconcile")
    db_session.refresh(attempt)
    assert second.status_code == 200
    assert second.json() == {"updated": 1}
    assert attempt.status == "paid"
    assert db_session.query(Payment).filter(
        Payment.reference == f"paynow:{attempt_id}"
    ).count() == 1

def test_initiation_rejects_untrusted_provider_checkout_url(
    client, db_session, monkeypatch
):
    school = School(
        code="PN007", name="Invalid Checkout URL School",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.flush()
    user = User(
        email="invalid-url-student@example.test", full_name="Invalid URL Student",
        password_hash="unused", role="student", school_id=school.id,
    )
    db_session.add(user)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PN-I1", first_name="Invalid",
        last_name="URL", status="active", portal_user_id=user.id,
    )
    db_session.add(student)
    db_session.flush()
    invoice = Invoice(
        school_id=school.id, student_id=student.id, invoice_number="PN-INV-I1",
        currency="USD", total=20, status="issued",
    )
    db_session.add(invoice)
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _student_principal(
        user.id, school.id
    )
    monkeypatch.setattr(
        paynow, "initiate_transaction",
        lambda **_kwargs: {
            "Status": "Ok",
            "hash_verified": True,
            "BrowserUrl": "https://attacker.example/checkout",
            "PollUrl": "https://www.paynow.co.zw/interface/checkpayment/?guid=abc",
        },
    )

    response = client.post(
        "/paynow/initiate",
        json={"invoice_ids": [invoice.id], "amount": 10},
    )

    assert response.status_code == 502
    attempt = db_session.query(PaynowAttempt).one()
    assert attempt.status == "failed"
    assert attempt.browser_url is None
    assert attempt.poll_url is None


def test_parent_cannot_pay_another_learners_invoice_within_same_school(
    client, db_session, monkeypatch
):
    school = School(
        code="PN008", name="Parent Invoice Ownership School",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.flush()
    linked_learner = Student(
        school_id=school.id, student_number="PN-P2", first_name="Linked",
        last_name="Learner", status="active",
    )
    other_learner = Student(
        school_id=school.id, student_number="PN-P3", first_name="Other",
        last_name="Learner", status="active",
    )
    db_session.add_all([linked_learner, other_learner])
    db_session.flush()
    other_invoice = Invoice(
        school_id=school.id, student_id=other_learner.id,
        invoice_number="PN-OTHER-INV", currency="USD", total=50,
        status="issued",
    )
    db_session.add(other_invoice)
    db_session.commit()

    parent = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=9005, school_id=school.id,
        role="parent", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: parent

    class VerifiedLinkResult:
        @staticmethod
        def first():
            return (1,)

    original_execute = db_session.execute

    def execute_with_verified_link(statement, *args, **kwargs):
        if "guardian_links" in str(statement):
            return VerifiedLinkResult()
        return original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", execute_with_verified_link)

    response = client.post(
        "/paynow/initiate",
        json={
            "student_id": linked_learner.id,
            "invoice_ids": [other_invoice.id],
            "amount": 10,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invoice does not belong to the selected student"
    assert db_session.query(PaynowAttempt).count() == 0


def test_student_paynow_rejects_ambiguous_active_learner_mapping(client, db_session):
    school = School(code="PN009", name="Ambiguous Paynow Mapping School")
    db_session.add(school)
    db_session.flush()
    user = User(
        email="ambiguous-paynow@example.test", full_name="Ambiguous Student",
        password_hash="unused", role="student", school_id=school.id,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add_all([
        Student(
            school_id=school.id, student_number="PN-A1", first_name="First",
            last_name="Learner", status="active", portal_user_id=user.id,
        ),
        Student(
            school_id=school.id, student_number="PN-A2", first_name="Second",
            last_name="Learner", status="active", portal_user_id=user.id,
        ),
    ])
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _student_principal(
        user.id, school.id
    )
    response = client.post("/paynow/initiate", json={"amount": 1})

    assert response.status_code == 403
    assert response.json()["detail"] == "Student account is not uniquely linked"
    assert db_session.query(PaynowAttempt).count() == 0


def test_student_paynow_rejects_active_and_inactive_duplicate_mappings(client, db_session):
    school = School(code="PN010", name="Historical Paynow Mapping School")
    db_session.add(school)
    db_session.flush()
    user = User(
        email="historical-paynow@example.test", full_name="Historical Student",
        password_hash="unused", role="student", school_id=school.id,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add_all([
        Student(
            school_id=school.id, student_number="PN-H1", first_name="Active",
            last_name="Learner", status="active", portal_user_id=user.id,
        ),
        Student(
            school_id=school.id, student_number="PN-H2", first_name="Inactive",
            last_name="Learner", status="inactive", portal_user_id=user.id,
        ),
    ])
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _student_principal(
        user.id, school.id
    )
    response = client.post("/paynow/initiate", json={"amount": 1})

    assert response.status_code == 403
    assert response.json()["detail"] == "Student account is not uniquely linked"
    assert db_session.query(PaynowAttempt).count() == 0


def test_verified_webhook_refuses_invoice_outside_attempt_tenant(
    client, db_session, monkeypatch
):
    first_school = School(
        code="PN011", name="Attempt Tenant",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    second_school = School(code="PN012", name="Foreign Invoice Tenant")
    db_session.add_all([first_school, second_school])
    db_session.flush()
    student = Student(
        school_id=first_school.id, student_number="PN-X1",
        first_name="Tenant", last_name="Student", status="active",
    )
    foreign_student = Student(
        school_id=second_school.id, student_number="PN-X2",
        first_name="Foreign", last_name="Student", status="active",
    )
    db_session.add_all([student, foreign_student])
    db_session.flush()
    foreign_invoice = Invoice(
        school_id=second_school.id, student_id=foreign_student.id,
        invoice_number="PN-FOREIGN-INV", currency="USD", total=20,
        status="issued",
    )
    db_session.add(foreign_invoice)
    db_session.flush()
    attempt = PaynowAttempt(
        school_id=first_school.id, student_id=student.id,
        invoice_id=foreign_invoice.id, reference="PN-CROSS-TENANT",
        amount=20, currency="USD", status="sent",
        poll_url="https://www.paynow.co.zw/interface/checkpayment/?guid=tenant",
    )
    db_session.add(attempt)
    db_session.commit()

    monkeypatch.setattr(
        paynow, "poll_transaction",
        lambda _url, _key: {
            "Status": "Paid", "reference": "PN-CROSS-TENANT",
            "amount": "20.00", "hash_verified": True,
        },
    )

    response = client.post("/paynow/webhook", data={"reference": attempt.reference})

    assert response.status_code == 200
    assert response.json()["status"] == "verified payment could not be matched to its invoice"
    assert db_session.query(Payment).count() == 0
    assert db_session.query(PaymentAllocation).count() == 0
    assert db_session.query(Receipt).count() == 0
    db_session.refresh(attempt)
    assert attempt.status == "unverified"


def test_late_cancellation_webhook_cannot_downgrade_paid_attempt(client, db_session, monkeypatch):
    school = School(
        code="PN013", name="Paid Attempt Protection",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PN-LATE-1",
        first_name="Paid", last_name="Learner", status="active",
    )
    db_session.add(student)
    db_session.flush()
    attempt = PaynowAttempt(
        school_id=school.id, student_id=student.id,
        reference="PN-ALREADY-PAID", amount=12, currency="USD",
        status="paid", poll_url="https://www.paynow.co.zw/interface/checkpayment/?guid=paid",
    )
    db_session.add(attempt)
    db_session.flush()
    payment = Payment(
        school_id=school.id, student_id=student.id, amount=12,
        currency="USD", method="paynow", reference=f"paynow:{attempt.id}",
    )
    db_session.add(payment)
    db_session.commit()

    def unexpected_poll(*_args, **_kwargs):
        raise AssertionError("A settled attempt must not be polled again")

    monkeypatch.setattr(paynow, "poll_transaction", unexpected_poll)
    response = client.post("/paynow/webhook", data={"reference": attempt.reference})

    assert response.status_code == 200
    assert response.json()["status"] == "already paid"
    db_session.refresh(attempt)
    assert attempt.status == "paid"
    assert db_session.query(Payment).filter(
        Payment.reference == f"paynow:{attempt.id}"
    ).count() == 1


def test_verified_paynow_attempt_is_not_settled_above_remaining_invoice_balance(
    client, db_session, monkeypatch
):
    school = School(
        code="PN014", name="No Overpayment Settlement",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PN-OVER-1",
        first_name="Balance", last_name="Student", status="active",
    )
    db_session.add(student)
    db_session.flush()
    invoice = Invoice(
        school_id=school.id, student_id=student.id,
        invoice_number="PN-OVER-INV", currency="USD", total=20,
        status="issued",
    )
    db_session.add(invoice)
    db_session.flush()
    prior_payment = Payment(
        school_id=school.id, student_id=student.id, amount=20,
        currency="USD", method="cash", reference="CASH-SETTLED-FIRST",
    )
    db_session.add(prior_payment)
    db_session.flush()
    db_session.add(PaymentAllocation(
        school_id=school.id, payment_id=prior_payment.id,
        invoice_id=invoice.id, amount=20,
    ))
    attempt = PaynowAttempt(
        school_id=school.id, student_id=student.id, invoice_id=invoice.id,
        reference="PN-STALE-BALANCE", amount=20, currency="USD",
        status="sent", poll_url="https://www.paynow.co.zw/interface/checkpayment/?guid=stale",
    )
    db_session.add(attempt)
    db_session.commit()

    monkeypatch.setattr(
        paynow, "poll_transaction",
        lambda _url, _key: {
            "Status": "Paid", "reference": "PN-STALE-BALANCE",
            "amount": "20.00", "hash_verified": True,
        },
    )

    response = client.post("/paynow/webhook", data={"reference": attempt.reference})

    assert response.status_code == 200
    assert response.json()["status"] == "verified payment could not be matched to its invoice"
    assert db_session.query(Payment).count() == 1
    assert db_session.query(PaymentAllocation).count() == 1
    assert db_session.query(Receipt).count() == 0
    db_session.refresh(attempt)
    assert attempt.status == "unverified"


def test_paynow_receipts_are_sequential_for_distinct_attempts_in_one_school(
    client, db_session, monkeypatch
):
    school = School(
        code="PN015", name="Paynow Receipt Sequence",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.flush()
    attempts = []
    for index in (1, 2):
        student = Student(
            school_id=school.id, student_number=f"PN-SEQ-{index}",
            first_name="Receipt", last_name=f"Student {index}", status="active",
        )
        db_session.add(student)
        db_session.flush()
        invoice = Invoice(
            school_id=school.id, student_id=student.id,
            invoice_number=f"PN-SEQ-INV-{index}", currency="USD",
            total=10, status="issued",
        )
        db_session.add(invoice)
        db_session.flush()
        attempt = PaynowAttempt(
            school_id=school.id, student_id=student.id, invoice_id=invoice.id,
            reference=f"PN-SEQ-{index}", amount=10, currency="USD",
            status="sent",
            poll_url=f"https://www.paynow.co.zw/interface/checkpayment/?guid=seq-{index}",
        )
        db_session.add(attempt)
        attempts.append(attempt)
    db_session.commit()

    def verified_poll(url, _key):
        index = "1" if "seq-1" in url else "2"
        return {
            "Status": "Paid", "reference": f"PN-SEQ-{index}",
            "amount": "10.00", "hash_verified": True,
        }

    monkeypatch.setattr(paynow, "poll_transaction", verified_poll)
    receipt_numbers = []
    for attempt in attempts:
        response = client.post("/paynow/webhook", data={"reference": attempt.reference})
        assert response.status_code == 200
        receipt_numbers.append(
            db_session.query(Receipt).filter(
                Receipt.payment_id == db_session.query(Payment).filter(
                    Payment.reference == f"paynow:{attempt.id}"
                ).one().id
            ).one().receipt_number
        )

    assert receipt_numbers == ["RCP-00001", "RCP-00002"]


def test_paynow_student_balance_aggregation_preserves_decimal_cents(db_session):
    school = School(code="PN016", name="Decimal Checkout Balance")
    db_session.add(school)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PN-DECIMAL-1",
        first_name="Decimal", last_name="Learner", status="active",
    )
    db_session.add(student)
    db_session.flush()
    db_session.add_all([
        Invoice(
            school_id=school.id, student_id=student.id,
            invoice_number="PN-DEC-1", currency="USD",
            total="0.10", status="issued",
        ),
        Invoice(
            school_id=school.id, student_id=student.id,
            invoice_number="PN-DEC-2", currency="USD",
            total="0.20", status="issued",
        ),
    ])
    db_session.commit()

    from decimal import Decimal
    assert paynow._student_usd_balance(db_session, school.id, student.id) == Decimal("0.30")


def test_initiation_rejects_unverified_provider_response_before_returning_checkout(
    client, db_session, monkeypatch
):
    school = School(
        code="PN017", name="Unverified Initiation Response",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.flush()
    user = User(
        email="unverified-initiation@example.test", full_name="Unverified Initiation",
        password_hash="unused", role="student", school_id=school.id,
    )
    db_session.add(user)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PN-INIT-VERIFY", first_name="Unverified",
        last_name="Initiation", status="active", portal_user_id=user.id,
    )
    db_session.add(student)
    db_session.flush()
    invoice = Invoice(
        school_id=school.id, student_id=student.id, invoice_number="PN-INIT-VERIFY-INV",
        currency="USD", total=20, status="issued",
    )
    db_session.add(invoice)
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _student_principal(
        user.id, school.id
    )
    monkeypatch.setattr(
        paynow, "initiate_transaction",
        lambda **_kwargs: {
            "status": "Ok",
            "hash_verified": False,
            "BrowserUrl": "https://www.paynow.co.zw/Payment/Confirm/123",
            "PollUrl": "https://www.paynow.co.zw/interface/checkpayment/?guid=abc",
        },
    )

    response = client.post(
        "/paynow/initiate",
        json={"invoice_ids": [invoice.id], "amount": 10},
    )

    assert response.status_code == 502
    assert "unverified checkout response" in response.json()["detail"]
    attempt = db_session.query(PaynowAttempt).one()
    assert attempt.status == "failed"
    assert attempt.browser_url is None
    assert attempt.poll_url is None


def test_unverified_callback_cannot_cancel_attempt_or_overwrite_provider_reference(
    client, db_session, monkeypatch
):
    school = School(
        code="PN018", name="Unverified Callback State",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.flush()
    attempt = PaynowAttempt(
        school_id=school.id, reference="PN-CALLBACK-UNVERIFIED",
        amount=12, currency="USD", status="sent",
        poll_url="https://www.paynow.co.zw/interface/checkpayment/?guid=callback-test",
        paynow_reference="provider-reference-before",
    )
    db_session.add(attempt)
    db_session.commit()

    poll_results = iter([
        {
            "Status": "Pending",
            "reference": "PN-CALLBACK-UNVERIFIED",
            "hash_verified": False,
        },
        {
            "Status": "Pending",
            "reference": "PN-CALLBACK-UNVERIFIED",
            "hash_verified": True,
        },
    ])
    monkeypatch.setattr(
        paynow, "poll_transaction",
        lambda _url, _key: next(poll_results),
    )
    callback = {
        "reference": attempt.reference,
        "status": "Cancelled",
        "paynowreference": "attacker-controlled-reference",
    }
    response = client.post("/paynow/webhook", data=callback)

    assert response.status_code == 200
    assert response.json()["status"] == "provider status could not be verified"
    db_session.refresh(attempt)
    assert attempt.status == "unverified"
    assert attempt.paynow_reference == "provider-reference-before"

    # Even a valid signed Pending poll must override a forged Cancelled
    # callback field; callback form data is only a wake-up signal.
    response = client.post("/paynow/webhook", data=callback)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    db_session.refresh(attempt)
    assert attempt.status == "sent"
    assert attempt.paynow_reference == "provider-reference-before"
    assert db_session.query(Payment).count() == 0


def test_reconcile_does_not_accept_unsigned_failed_status(
    client, db_session, monkeypatch
):
    from app.services import paynow as paynow_service

    school = School(
        code="PN019", name="Unsigned Reconcile Status",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.flush()
    attempt = PaynowAttempt(
        school_id=school.id, reference="PN-RECONCILE-UNSIGNED",
        amount=8, currency="USD", status="sent",
        poll_url="https://www.paynow.co.zw/interface/checkpayment/?guid=reconcile-test",
    )
    db_session.add(attempt)
    db_session.commit()

    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=1, school_id=None,
        role="vortex_admin", is_admin=True,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal
    monkeypatch.setattr(
        paynow_service, "poll_transaction",
        lambda _url, _key: {
            "Status": "Failed",
            "reference": "PN-RECONCILE-UNSIGNED",
            "hash_verified": False,
        },
    )

    response = client.post("/paynow/reconcile")

    assert response.status_code == 200
    assert response.json() == {"updated": 1}
    db_session.refresh(attempt)
    assert attempt.status == "unverified"
    assert db_session.query(Payment).count() == 0


def test_signed_paynow_cancellation_status_is_accepted_from_provider_poll(
    client, db_session, monkeypatch
):
    school = School(
        code="PN020", name="Signed Cancellation Status",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.flush()
    attempt = PaynowAttempt(
        school_id=school.id, reference="PN-SIGNED-CANCEL",
        amount=8, currency="USD", status="sent",
        poll_url="https://www.paynow.co.zw/interface/checkpayment/?guid=signed-cancel",
    )
    db_session.add(attempt)
    db_session.commit()

    monkeypatch.setattr(
        paynow, "poll_transaction",
        lambda _url, _key: {
            "Status": "Cancelled",
            "reference": "PN-SIGNED-CANCEL",
            "hash_verified": True,
        },
    )

    response = client.post(
        "/paynow/webhook",
        data={"reference": attempt.reference, "status": "Pending"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    db_session.refresh(attempt)
    assert attempt.status == "cancelled"



def test_only_vortex_platform_admin_can_run_cross_school_reconciliation(client):
    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=999, school_id=None,
        role="vortex_support", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal
    response = client.post("/paynow/reconcile")
    assert response.status_code == 403

def test_school_user_cannot_request_paynow_settings_for_another_school(client, db_session):
    own = School(code="PN007", name="Own Paynow School")
    other = School(code="PN008", name="Other Paynow School")
    db_session.add_all([own, other])
    db_session.commit()
    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=7007, school_id=own.id,
        role="owner", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    read_response = client.get(f"/paynow/settings?school_id={other.id}")
    write_response = client.post("/paynow/settings", json={
        "school_id": other.id,
        "integration_id": "foreign",
        "integration_key": "must-not-be-stored",
        "test_mode": True,
    })

    assert read_response.status_code == 403
    assert write_response.status_code == 403




def test_paynow_idempotency_lookup_is_scoped_to_attempt_school(db_session):
    own_school = School(code="PN021", name="Settlement Tenant")
    foreign_school = School(code="PN022", name="Foreign Existing Payment")
    db_session.add_all([own_school, foreign_school])
    db_session.flush()
    own_student = Student(
        school_id=own_school.id, student_number="PN-SCOPE-OWN",
        first_name="Own", last_name="Learner", status="active",
    )
    foreign_student = Student(
        school_id=foreign_school.id, student_number="PN-SCOPE-FOREIGN",
        first_name="Foreign", last_name="Learner", status="active",
    )
    db_session.add_all([own_student, foreign_student])
    db_session.flush()
    invoice = Invoice(
        school_id=own_school.id, student_id=own_student.id,
        invoice_number="PN-SCOPE-INV", currency="USD", total=12,
        status="issued",
    )
    db_session.add(invoice)
    db_session.flush()
    attempt = PaynowAttempt(
        school_id=own_school.id, student_id=own_student.id,
        invoice_id=invoice.id, reference="PN-SCOPE-ATTEMPT",
        amount=12, currency="USD", status="sent",
    )
    db_session.add(attempt)
    db_session.flush()
    foreign_payment = Payment(
        school_id=foreign_school.id, student_id=foreign_student.id,
        amount=12, currency="USD", method="paynow",
        reference=f"paynow:{attempt.id}",
    )
    db_session.add(foreign_payment)
    db_session.commit()

    assert paynow._record_verified_payment(db_session, attempt) is True

    own_payment = db_session.query(Payment).filter(
        Payment.school_id == own_school.id,
        Payment.reference == f"paynow:{attempt.id}",
    ).one()
    assert own_payment.id != foreign_payment.id
    assert db_session.query(Payment).filter(
        Payment.school_id == own_school.id,
        Payment.reference == f"paynow:{attempt.id}",
    ).count() == 1
    assert db_session.query(Receipt).filter(
        Receipt.payment_id == own_payment.id,
    ).count() == 1
