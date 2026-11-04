from decimal import Decimal

from app.models.payment import Invoice, Payment, PaymentAllocation
from app.models.school import School
from app.models.student import Student
from app.services.money import allocate_payment, invoice_balance, student_balance


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


def test_invoice_balance_ignores_allocations_from_another_school(db_session):
    school, student, usd, _ = _records(db_session)
    foreign_school = School(code="MONEY2", name="Foreign Money School")
    db_session.add(foreign_school)
    db_session.flush()
    foreign_student = Student(
        school_id=foreign_school.id,
        student_number="M002",
        first_name="Foreign",
        last_name="Learner",
        status="active",
    )
    db_session.add(foreign_student)
    db_session.flush()
    foreign_payment = Payment(
        school_id=foreign_school.id,
        student_id=foreign_student.id,
        amount=Decimal("40.00"),
        currency="USD",
        method="cash",
    )
    db_session.add(foreign_payment)
    db_session.flush()
    # Simulate a malformed cross-tenant allocation row. The invoice balance
    # must not treat another school's payment as money received by this school.
    db_session.add(PaymentAllocation(
        school_id=school.id,
        payment_id=foreign_payment.id,
        invoice_id=usd.id,
        amount=Decimal("40.00"),
    ))
    db_session.commit()

    assert invoice_balance(db_session, usd) == Decimal("100.00")


def test_invoice_balance_ignores_allocations_from_another_student_in_same_school(db_session):
    school, student, usd, _ = _records(db_session)
    other_student = Student(
        school_id=school.id,
        student_number="M003",
        first_name="Other",
        last_name="Learner",
        status="active",
    )
    db_session.add(other_student)
    db_session.flush()
    other_payment = Payment(
        school_id=school.id,
        student_id=other_student.id,
        amount=Decimal("35.00"),
        currency="USD",
        method="cash",
    )
    db_session.add(other_payment)
    db_session.flush()
    db_session.add(PaymentAllocation(
        school_id=school.id,
        payment_id=other_payment.id,
        invoice_id=usd.id,
        amount=Decimal("35.00"),
    ))
    db_session.commit()

    assert invoice_balance(db_session, usd) == Decimal("100.00")
    assert student_balance(db_session, school.id, student.id, "USD") == Decimal("100.00")


def test_student_balance_uses_school_scoped_payment_totals(db_session):
    school, student, usd, _ = _records(db_session)
    payment = Payment(
        school_id=school.id,
        student_id=student.id,
        amount=Decimal("30.00"),
        currency="USD",
        method="cash",
    )
    db_session.add(payment)
    db_session.flush()
    db_session.add(PaymentAllocation(
        school_id=school.id,
        payment_id=payment.id,
        invoice_id=usd.id,
        amount=Decimal("30.00"),
    ))
    db_session.commit()

    assert student_balance(db_session, school.id, student.id, "USD") == Decimal("70.00")
