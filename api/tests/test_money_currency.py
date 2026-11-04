from decimal import Decimal

from app.models.payment import Invoice, Payment, PaymentAllocation
from app.models.school import School
from app.models.student import Student
from app.services.money import allocate_payment, invoice_balance


def _records(db_session):
    school = School(code="MONEY1", name="Money Test School")
    db_session.add(school)
    db_session.flush()
    student = Student(
        school_id=school.id,
        student_number="M001",
        first_name="Test",
        last_name="Learner",
        status="active",
    )
    db_session.add(student)
    db_session.flush()
    usd = Invoice(
        school_id=school.id,
        student_id=student.id,
        invoice_number="USD-001",
        currency="USD",
        total=Decimal("100.00"),
        status="issued",
    )
    zwl = Invoice(
        school_id=school.id,
        student_id=student.id,
        invoice_number="ZWL-001",
        currency="ZWL",
        total=Decimal("500.00"),
        status="issued",
    )
    db_session.add_all([usd, zwl])
    db_session.commit()
    return school, student, usd, zwl


def test_automatic_allocation_never_crosses_currencies(db_session):
    _, student, usd, zwl = _records(db_session)
    payment = Payment(
        school_id=usd.school_id,
        student_id=student.id,
        amount=Decimal("30.00"),
        currency="USD",
        method="cash",
    )
    db_session.add(payment)
    db_session.flush()

    allocate_payment(db_session, payment)
    db_session.commit()

    assert invoice_balance(db_session, usd) == Decimal("70.00")
    assert invoice_balance(db_session, zwl) == Decimal("500.00")
    allocations = db_session.query(PaymentAllocation).filter(
        PaymentAllocation.payment_id == payment.id
    ).all()
    assert len(allocations) == 1
    assert allocations[0].invoice_id == usd.id


def test_invoice_balance_ignores_mismatched_currency_allocations(db_session):
    _, student, usd, _ = _records(db_session)
    wrong_currency_payment = Payment(
        school_id=usd.school_id,
        student_id=student.id,
        amount=Decimal("25.00"),
        currency="ZWL",
        method="cash",
    )
    db_session.add(wrong_currency_payment)
    db_session.flush()
    db_session.add(PaymentAllocation(
        school_id=usd.school_id,
        payment_id=wrong_currency_payment.id,
        invoice_id=usd.id,
        amount=Decimal("25.00"),
    ))
    db_session.commit()

    assert invoice_balance(db_session, usd) == Decimal("100.00")
