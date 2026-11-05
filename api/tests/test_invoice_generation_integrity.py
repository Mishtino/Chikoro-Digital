import pytest
from sqlalchemy.exc import IntegrityError

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.fee import FeeStructure, FeeStructureItem, Term
from app.models.payment import Invoice
from app.models.school import School
from app.models.student import Student


def _owner(school_id):
    from uuid import uuid4
    return SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=7101,
        school_id=school_id,
        role="owner",
        is_admin=False,
    )


def test_invoice_generation_is_idempotent_for_each_student_and_term(client, db_session):
    school = School(code="INVGEN01", name="Invoice Generation")
    db_session.add(school)
    db_session.flush()
    term = Term(
        school_id=school.id, name="Term 1", academic_year="2027",
        is_current=True,
    )
    students = [
        Student(
            school_id=school.id, student_number=f"INVGEN-{index}",
            first_name="Learner", last_name=str(index), status="active",
            form="Form 1",
        )
        for index in (1, 2)
    ]
    db_session.add_all([term, *students])
    db_session.flush()
    structure = FeeStructure(
        school_id=school.id, term_id=term.id, form="Form 1",
        name="Form 1 Term 1",
    )
    db_session.add(structure)
    db_session.flush()
    db_session.add(FeeStructureItem(
        school_id=school.id, fee_structure_id=structure.id,
        description="Tuition", amount=100, currency="USD",
    ))
    db_session.commit()

    app.dependency_overrides[get_supabase_principal] = lambda: _owner(school.id)

    first = client.post(
        "/fees/invoices/generate",
        json={"term_id": term.id, "form": "Form 1"},
    )
    second = client.post(
        "/fees/invoices/generate",
        json={"term_id": term.id, "form": "Form 1"},
    )

    assert first.status_code == 200
    assert first.json() == {"created": 2}
    assert second.status_code == 200
    assert second.json() == {"created": 0}
    invoices = db_session.query(Invoice).filter(
        Invoice.school_id == school.id,
        Invoice.term_id == term.id,
    ).all()
    assert len(invoices) == 2
    assert {invoice.student_id for invoice in invoices} == {
        student.id for student in students
    }


def test_database_rejects_duplicate_invoice_for_same_student_and_term(db_session):
    school = School(code="INVGEN02", name="Invoice Uniqueness")
    db_session.add(school)
    db_session.flush()
    student = Student(
        school_id=school.id, student_number="INVGEN-UNIQUE",
        first_name="Unique", last_name="Learner", status="active",
    )
    term = Term(
        school_id=school.id, name="Term 1", academic_year="2027",
    )
    db_session.add_all([student, term])
    db_session.flush()
    db_session.add(Invoice(
        school_id=school.id, student_id=student.id, term_id=term.id,
        invoice_number="INV-UNIQUE-1", currency="USD", total=100,
    ))
    db_session.commit()

    db_session.add(Invoice(
        school_id=school.id, student_id=student.id, term_id=term.id,
        invoice_number="INV-UNIQUE-2", currency="USD", total=100,
    ))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
