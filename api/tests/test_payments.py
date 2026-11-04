from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.payment import Invoice, Payment, PaymentAllocation, Receipt
from app.models.school import School
from app.models.student import Student


def _owner(school_id):
    return SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=7001,
        school_id=school_id,
        role="owner",
        is_admin=False,
    )


def test_manual_payment_locks_balance_and_rejects_subsequent_overpayment(
    client, db_session
):
    school = School(code="PAY001", name="Manual Payment Integrity")
    db_session.add(school)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PAY-STU-1",
        first_name="Manual", last_name="Payment", status="active",
    )
    db_session.add(student)
    db_session.flush()
    invoice = Invoice(
        school_id=school.id, student_id=student.id,
        invoice_number="PAY-INV-1", currency="USD", total=100,
        status="issued",
    )
    db_session.add(invoice)
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _owner(school.id)

    first = client.post(
        "/payments",
        json={"student_id": student.id, "amount": 80, "currency": "USD",
              "method": "cash", "invoice_ids": [invoice.id]},
    )
    second = client.post(
        "/payments",
        json={"student_id": student.id, "amount": 30, "currency": "USD",
              "method": "cash", "invoice_ids": [invoice.id]},
    )

    assert first.status_code == 201
    assert first.json()["receipt_number"] == "RCP-00001"
    assert second.status_code == 422
    assert second.json()["detail"] == "Payment amount exceeds the selected invoices' outstanding balance"
    assert db_session.query(Payment).count() == 1
    assert db_session.query(PaymentAllocation).count() == 1
    assert db_session.query(Receipt).count() == 1


def test_manual_receipts_are_sequential_within_school(client, db_session):
    school = School(code="PAY002", name="Receipt Sequence School")
    db_session.add(school)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PAY-STU-2",
        first_name="Receipt", last_name="Student", status="active",
    )
    db_session.add(student)
    db_session.flush()
    invoices = [
        Invoice(
            school_id=school.id, student_id=student.id,
            invoice_number=f"PAY-INV-{i}", currency="USD", total=10,
            status="issued",
        )
        for i in (2, 3)
    ]
    db_session.add_all(invoices)
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _owner(school.id)
    receipt_numbers = []
    for invoice in invoices:
        response = client.post(
            "/payments",
            json={"student_id": student.id, "amount": 10, "currency": "USD",
                  "method": "cash", "invoice_ids": [invoice.id]},
        )
        assert response.status_code == 201
        receipt_numbers.append(response.json()["receipt_number"])

    assert receipt_numbers == ["RCP-00001", "RCP-00002"]
