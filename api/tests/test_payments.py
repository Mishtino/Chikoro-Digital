import pytest
from sqlalchemy.exc import IntegrityError

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


def test_manual_receipt_numbering_does_not_reuse_existing_gap(client, db_session):
    school = School(code="PAY003", name="Receipt Gap School")
    db_session.add(school)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PAY-STU-3",
        first_name="Gap", last_name="Student", status="active",
    )
    db_session.add(student)
    db_session.flush()
    invoice = Invoice(
        school_id=school.id, student_id=student.id,
        invoice_number="PAY-INV-GAP", currency="USD", total=50,
        status="issued",
    )
    db_session.add(invoice)
    db_session.flush()
    old_payments = [
        Payment(
            school_id=school.id, student_id=student.id,
            amount=1, currency="USD", method="cash",
        )
        for _ in range(2)
    ]
    db_session.add_all(old_payments)
    db_session.flush()
    db_session.add_all([
        Receipt(school_id=school.id, payment_id=old_payments[0].id,
                receipt_number="RCP-00001"),
        Receipt(school_id=school.id, payment_id=old_payments[1].id,
                receipt_number="RCP-00003"),
    ])
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _owner(school.id)
    response = client.post(
        "/payments",
        json={"student_id": student.id, "amount": 10, "currency": "USD",
              "method": "cash", "invoice_ids": [invoice.id]},
    )

    assert response.status_code == 201
    assert response.json()["receipt_number"] == "RCP-00004"


def test_payment_reference_is_unique_per_school(db_session):
    first_school = School(code="PAY004", name="Reference Tenant One")
    second_school = School(code="PAY005", name="Reference Tenant Two")
    db_session.add_all([first_school, second_school])
    db_session.flush()
    first_student = Student(
        school_id=first_school.id, student_number="PAY-REF-1",
        first_name="Reference", last_name="One", status="active",
    )
    second_student = Student(
        school_id=second_school.id, student_number="PAY-REF-2",
        first_name="Reference", last_name="Two", status="active",
    )
    db_session.add_all([first_student, second_student])
    db_session.flush()
    db_session.add(Payment(
        school_id=first_school.id, student_id=first_student.id,
        amount=10, currency="USD", method="bank", reference="BANK-REF-1",
    ))
    db_session.commit()

    # A different school may legitimately receive the same external reference.
    db_session.add(Payment(
        school_id=second_school.id, student_id=second_student.id,
        amount=10, currency="USD", method="bank", reference="BANK-REF-1",
    ))
    db_session.commit()

    db_session.add(Payment(
        school_id=first_school.id, student_id=first_student.id,
        amount=5, currency="USD", method="cash", reference="BANK-REF-1",
    ))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_payment_cannot_allocate_twice_to_same_invoice(db_session):
    school = School(code="PAY006", name="Allocation Uniqueness School")
    db_session.add(school)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PAY-ALLOC-1",
        first_name="Allocation", last_name="Student", status="active",
    )
    db_session.add(student)
    db_session.flush()
    invoice = Invoice(
        school_id=school.id, student_id=student.id,
        invoice_number="PAY-ALLOC-INV", currency="USD", total=20,
        status="issued",
    )
    db_session.add(invoice)
    db_session.flush()
    payment = Payment(
        school_id=school.id, student_id=student.id,
        amount=10, currency="USD", method="cash",
    )
    db_session.add(payment)
    db_session.commit()

    db_session.add(PaymentAllocation(
        school_id=school.id, payment_id=payment.id,
        invoice_id=invoice.id, amount=5,
    ))
    db_session.commit()
    db_session.add(PaymentAllocation(
        school_id=school.id, payment_id=payment.id,
        invoice_id=invoice.id, amount=5,
    ))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_manual_payment_returns_conflict_for_duplicate_school_reference(
    client, db_session
):
    school = School(code="PAY007", name="Duplicate Reference API")
    db_session.add(school)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PAY-REF-API",
        first_name="Reference", last_name="API", status="active",
    )
    db_session.add(student)
    db_session.flush()
    invoices = [
        Invoice(
            school_id=school.id, student_id=student.id,
            invoice_number=f"PAY-REF-API-{index}", currency="USD",
            total=20, status="issued",
        )
        for index in (1, 2)
    ]
    db_session.add_all(invoices)
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _owner(school.id)

    first = client.post(
        "/payments",
        json={
            "student_id": student.id, "amount": 5, "currency": "USD",
            "method": "bank", "reference": " BANK-API-REF ",
            "invoice_ids": [invoices[0].id],
        },
    )
    duplicate = client.post(
        "/payments",
        json={
            "student_id": student.id, "amount": 5, "currency": "USD",
            "method": "bank", "reference": "BANK-API-REF",
            "invoice_ids": [invoices[1].id],
        },
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Payment reference already exists for this school"
    payments = db_session.query(Payment).filter(Payment.school_id == school.id).all()
    assert len(payments) == 1
    assert payments[0].reference == "BANK-API-REF"



def test_voided_payment_is_excluded_from_invoice_paid_balance(client, db_session):
    school = School(code="PAY010", name="Voided Payment Balance")
    db_session.add(school)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PAY-VOID-1",
        first_name="Void", last_name="Payment", status="active",
    )
    db_session.add(student)
    db_session.flush()
    invoice = Invoice(
        school_id=school.id, student_id=student.id,
        invoice_number="PAY-VOID-INV", currency="USD", total=100,
        status="issued",
    )
    db_session.add(invoice)
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _owner(school.id)

    recorded = client.post(
        "/payments",
        json={"student_id": student.id, "amount": 60, "currency": "USD",
              "method": "cash", "invoice_ids": [invoice.id]},
    )
    assert recorded.status_code == 201
    payment_id = recorded.json()["payment_id"]

    voided = client.post(
        f"/payments/{payment_id}/void",
        json={"reason": "Duplicate cash entry"},
    )
    assert voided.status_code == 200
    assert voided.json() == {"status": "voided"}

    db_session.refresh(invoice)
    from app.services.money import invoice_balance
    assert invoice_balance(db_session, invoice) == 100
    payment = db_session.query(Payment).filter(Payment.id == payment_id).one()
    assert payment.voided is True
    assert payment.void_reason == "Duplicate cash entry"


def test_voiding_a_payment_twice_is_rejected(client, db_session):
    school = School(code="PAY011", name="Repeated Void Guard")
    db_session.add(school)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PAY-VOID-2",
        first_name="Repeat", last_name="Void", status="active",
    )
    db_session.add(student)
    db_session.flush()
    invoice = Invoice(
        school_id=school.id, student_id=student.id,
        invoice_number="PAY-VOID-INV-2", currency="USD", total=30,
        status="issued",
    )
    db_session.add(invoice)
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _owner(school.id)

    recorded = client.post(
        "/payments",
        json={"student_id": student.id, "amount": 10, "currency": "USD",
              "method": "cash", "invoice_ids": [invoice.id]},
    )
    assert recorded.status_code == 201
    payment_id = recorded.json()["payment_id"]
    first = client.post(f"/payments/{payment_id}/void", json={"reason": "Correction"})
    second = client.post(f"/payments/{payment_id}/void", json={"reason": "Repeated correction"})

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["detail"] == "Already voided"


def test_payment_reads_reject_mismatched_school_filter(client, db_session):
    school = School(code="PAY008", name="Payment Tenant Scope")
    other_school = School(code="PAY009", name="Other Payment Tenant")
    db_session.add_all([school, other_school])
    db_session.flush()
    app.dependency_overrides[get_supabase_principal] = lambda: _owner(school.id)

    payments = client.get(f"/payments?school_id={other_school.id}")
    invoices = client.get(f"/invoices?school_id={other_school.id}")

    assert payments.status_code == 403
    assert invoices.status_code == 403


def test_payment_and_invoice_detail_reads_hide_other_school_records(client, db_session):
    school = School(code="PAY010", name="Payment Detail Tenant")
    other_school = School(code="PAY011", name="Other Payment Detail Tenant")
    db_session.add_all([school, other_school])
    db_session.flush()
    student = Student(
        school_id=other_school.id, student_number="PAY-OTHER-1",
        first_name="Other", last_name="Tenant", status="active",
    )
    db_session.add(student)
    db_session.flush()
    invoice = Invoice(
        school_id=other_school.id, student_id=student.id,
        invoice_number="PAY-OTHER-INV", currency="USD", total=20,
        status="issued",
    )
    db_session.add(invoice)
    db_session.flush()
    payment = Payment(
        school_id=other_school.id, student_id=student.id,
        amount=5, currency="USD", method="cash",
    )
    db_session.add(payment)
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _owner(school.id)

    invoice_response = client.get(f"/invoices/{invoice.id}")
    payment_response = client.post(
        f"/payments/{payment.id}/void",
        json={"reason": "cross-tenant test"},
    )

    assert invoice_response.status_code == 404
    assert payment_response.status_code == 404
