from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.school import School
from app.models.student import Student
from app.models.user import User
from app.models.fee import Term


def _principal(user, role="owner", is_admin=False):
    return SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=user.id,
        school_id=user.school_id,
        role=role,
        is_admin=is_admin,
    )


def test_school_admin_overview_is_scoped_to_authenticated_school(client, seed_two_schools, db_session):
    owner = seed_two_schools["u1"]
    other_school_id = seed_two_schools["u2"].school_id
    db_session.add(Student(
        school_id=owner.school_id,
        student_number=f"{owner.school_id}-DASH-1",
        first_name="A",
        last_name="Learner",
        status="active",
    ))
    db_session.add(Student(
        school_id=other_school_id,
        student_number=f"{other_school_id}-DASH-1",
        first_name="B",
        last_name="Learner",
        status="active",
    ))
    db_session.add(Term(
        school_id=owner.school_id,
        name="Term 1",
        academic_year="2027",
        is_current=True,
    ))
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(owner)
    response = client.get("/school-admin/overview")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["school"]["id"] == owner.school_id
    assert data["students"]["total"] == 1
    assert data["academics"]["current_term"]["name"] == "Term 1"


def test_school_admin_overview_denies_non_school_admin(client, seed_two_schools):
    teacher = seed_two_schools["u1"]
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(teacher, role="teacher")
    response = client.get("/school-admin/overview")
    assert response.status_code == 403


def test_school_admin_overview_denies_platform_admin(client, seed_two_schools):
    admin = seed_two_schools["u1"]
    app.dependency_overrides[get_supabase_principal] = lambda: _principal(admin, role="vortex_admin", is_admin=True)
    response = client.get("/school-admin/overview")
    assert response.status_code == 403


def test_school_admin_overview_aggregates_only_valid_school_payment_allocations(
    client, seed_two_schools, db_session
):
    from decimal import Decimal
    from app.models.payment import Invoice, Payment, PaymentAllocation

    owner = seed_two_schools["u1"]
    learner = Student(
        school_id=owner.school_id,
        student_number=f"{owner.school_id}-DASH-FEE",
        first_name="Fee",
        last_name="Learner",
        status="active",
    )
    db_session.add(learner)
    db_session.flush()
    invoice = Invoice(
        school_id=owner.school_id,
        student_id=learner.id,
        invoice_number="DASH-INV-1",
        currency="USD",
        total=Decimal("100.00"),
        status="issued",
    )
    db_session.add(invoice)
    db_session.flush()
    payment = Payment(
        school_id=owner.school_id,
        student_id=learner.id,
        amount=Decimal("60.00"),
        currency="USD",
        method="manual",
        voided=False,
    )
    db_session.add(payment)
    db_session.flush()
    db_session.add(PaymentAllocation(
        school_id=owner.school_id,
        payment_id=payment.id,
        invoice_id=invoice.id,
        amount=Decimal("60.00"),
    ))
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _principal(owner)
    response = client.get("/school-admin/overview")
    assert response.status_code == 200, response.text
    assert response.json()["finance"]["open_invoices"] == 1
    assert response.json()["finance"]["outstanding_by_currency"] == {"USD": "40.00"}
