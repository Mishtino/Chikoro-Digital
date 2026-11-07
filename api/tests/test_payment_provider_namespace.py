import pytest
from app.deps_supabase import get_supabase_principal
from app.main import app
from app.models.payment import Invoice, Payment, Receipt
from app.models.school import School
from app.models.student import Student
from uuid import uuid4
from app.deps_supabase import SupabasePrincipal


def _owner(school_id):
    return SupabasePrincipal(
        auth_user_id=uuid4(), user_id=7001, school_id=school_id,
        role="owner", is_admin=False,
    )


@pytest.mark.parametrize("method,reference", [
    ("paynow", "MANUAL-1"),
    (" PayNow ", "MANUAL-2"),
    ("cash", "paynow:123"),
    ("bank", "PAYNOW:456"),
])
def test_manual_endpoint_cannot_impersonate_verified_paynow(
    client, db_session, method, reference
):
    school = School(code="PAY-RESERVED", name="Reserved Provider Reference")
    db_session.add(school)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="PAY-RESERVED-STUDENT",
        first_name="Reserved", last_name="Reference", status="active",
    )
    db_session.add(student)
    db_session.flush()
    db_session.add(Invoice(
        school_id=school.id, student_id=student.id,
        invoice_number="PAY-RESERVED-INV", currency="USD",
        total=100, status="issued",
    ))
    db_session.commit()
    app.dependency_overrides[get_supabase_principal] = lambda: _owner(school.id)
    response = client.post("/payments", json={
        "student_id": student.id, "amount": 10, "currency": "USD",
        "method": method, "reference": reference,
    })
    assert response.status_code == 422
    assert response.json()["detail"] == "Paynow payments must be recorded through verified provider settlement"
    assert db_session.query(Payment).count() == 0
    assert db_session.query(Receipt).count() == 0
