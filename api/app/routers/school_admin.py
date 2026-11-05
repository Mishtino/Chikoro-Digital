from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.models.school import School
from app.models.student import Student
from app.models.user import User
from app.models.fee import Term
from app.models.payment import Invoice
from app.models.results import Subject, Assessment, Mark
from app.services.money import invoice_balance

router = APIRouter(prefix="/school-admin", tags=["school-admin"])

SCHOOL_ADMIN_ROLES = {"owner", "headmaster"}
STAFF_ROLES = ("owner", "headmaster", "bursar", "teacher")


@router.get("/overview")
def school_admin_overview(
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    if principal.is_admin or principal.role not in SCHOOL_ADMIN_ROLES or principal.school_id is None:
        raise HTTPException(status_code=403, detail="School administrator access required")

    school = db.get(School, principal.school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")

    school_id = school.id
    student_query = db.query(Student).filter(Student.school_id == school_id)
    total_students = student_query.count()
    active_students = student_query.filter(Student.status == "active").count()
    active_staff = db.query(User).filter(
        User.school_id == school_id,
        User.role.in_(STAFF_ROLES),
        User.is_active.is_(True),
        User.is_admin.is_(False),
    ).count()
    disabled_staff = db.query(User).filter(
        User.school_id == school_id,
        User.role.in_(STAFF_ROLES),
        User.is_active.is_(False),
        User.is_admin.is_(False),
    ).count()

    current_term = db.query(Term).filter(
        Term.school_id == school_id, Term.is_current.is_(True)
    ).order_by(Term.id.desc()).first()

    invoices = db.query(Invoice).filter(
        Invoice.school_id == school_id, Invoice.status != "void"
    ).all()
    open_invoices = 0
    outstanding = defaultdict(lambda: Decimal("0"))
    for invoice in invoices:
        balance = invoice_balance(db, invoice)
        if balance > 0:
            open_invoices += 1
            outstanding[invoice.currency] += balance

    mark_counts = {
        state: db.query(Mark).filter(
            Mark.school_id == school_id, Mark.status == state
        ).count()
        for state in ("draft", "approved", "published")
    }

    return {
        "school": {
            "id": school.id,
            "code": school.code,
            "name": school.name,
            "province": school.province,
            "status": school.status,
            "plan": school.plan,
        },
        "students": {
            "total": total_students,
            "active": active_students,
            "inactive": total_students - active_students,
        },
        "staff": {"active": active_staff, "disabled": disabled_staff},
        "academics": {
            "current_term": (
                {
                    "id": current_term.id,
                    "name": current_term.name,
                    "academic_year": current_term.academic_year,
                }
                if current_term else None
            ),
            "subjects": db.query(Subject).filter(Subject.school_id == school_id).count(),
            "assessments": db.query(Assessment).filter(Assessment.school_id == school_id).count(),
            "marks": mark_counts,
        },
        "finance": {
            "open_invoices": open_invoices,
            "outstanding_by_currency": {
                currency: format(amount, ".2f")
                for currency, amount in sorted(outstanding.items())
            },
        },
    }
