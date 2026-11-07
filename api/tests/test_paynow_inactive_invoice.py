from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.paynow import PaynowAttempt
from app.models.payment import Invoice
from app.models.school import School
from app.models.student import Student
from app.routers import paynow
from app.services.crypto import encrypt


def test_invoice_only_checkout_rejects_inactive_student(client, db_session, monkeypatch):
    school = School(
        code="PN-INACTIVE", name="Inactive Checkout School",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PN-INACTIVE-STU",
        first_name="Inactive", last_name="Learner", status="inactive",
    )
    db_session.add(student)
    db_session.flush()
    invoice = Invoice(
        school_id=school.id, student_id=student.id,
        invoice_number="PN-INACTIVE-INV", currency="USD",
        total=20, status="issued",
    )
    db_session.add(invoice)
    db_session.commit()
    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=7101, school_id=school.id,
        role="bursar", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    def unexpected_provider_call(**kwargs):
        raise AssertionError("Inactive learner must not reach provider checkout")

    monkeypatch.setattr(paynow, "initiate_transaction", unexpected_provider_call)
    response = client.post(
        "/paynow/initiate",
        json={"invoice_ids": [invoice.id], "school_id": school.id},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Active student not found"
    assert db_session.query(PaynowAttempt).count() == 0
