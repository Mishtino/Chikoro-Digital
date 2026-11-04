from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.deps_supabase import get_supabase_principal, SupabasePrincipal
from app.models.student import Student, Contact
from app.models.payment import Invoice
from app.services.money import invoice_balance, student_balance

router = APIRouter(prefix="/portal", tags=["portal"])


class PortalRegisterRequest(BaseModel):
    school_code: str
    student_number: str
    pin: str
    password: str
    email: Optional[str] = None
    phone: Optional[str] = None


class PortalFeeItem(BaseModel):
    invoice_number: str
    total: float
    balance: float
    currency: str
    issued_at: Optional[str] = None



def _parent_student_ids(principal: SupabasePrincipal, db: Session) -> list[int]:
    if principal.role != "parent":
        raise HTTPException(status_code=403, detail="Parent portal only")
    if principal.school_id is None:
        raise HTTPException(status_code=403, detail="School context required")
    rows = db.execute(text("""
        SELECT DISTINCT c.student_id
        FROM public.guardian_links AS gl
        JOIN public.contacts AS c
          ON c.id = gl.contact_id AND c.school_id = gl.school_id
        JOIN public.students AS s
          ON s.id = c.student_id AND s.school_id = c.school_id
        WHERE gl.profile_id = :profile_id
          AND gl.school_id = :school_id
          AND gl.is_active = true
          AND gl.verified_at IS NOT NULL
          AND s.status = 'active'
    """), {
        "profile_id": str(principal.auth_user_id),
        "school_id": principal.school_id,
    }).all()
    return [row[0] for row in rows]


def _parent_student(principal: SupabasePrincipal, student_id: int, db: Session) -> Student:
    allowed_ids = _parent_student_ids(principal, db)
    if student_id not in allowed_ids:
        raise HTTPException(status_code=404, detail="Linked student not found")
    student = db.query(Student).filter(
        Student.id == student_id,
        Student.school_id == principal.school_id,
        Student.status == "active",
    ).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Linked student not found")
    return student


@router.get("/parent/children")
def parent_children(principal: SupabasePrincipal = Depends(get_supabase_principal), db: Session = Depends(get_db)):
    student_ids = _parent_student_ids(principal, db)
    if not student_ids:
        return {"children": []}
    children = db.query(Student).filter(
        Student.id.in_(student_ids),
        Student.school_id == principal.school_id,
        Student.status == "active",
    ).order_by(Student.last_name, Student.first_name).all()
    return {
        "children": [
            {
                "id": student.id,
                "student_number": student.student_number,
                "name": f"{student.first_name} {student.last_name}",
                "form": student.form,
            }
            for student in children
        ]
    }


@router.get("/parent/children/{student_id}/fee-status")
def parent_child_fee_status(student_id: int, principal: SupabasePrincipal = Depends(get_supabase_principal), db: Session = Depends(get_db)):
    student = _parent_student(principal, student_id, db)
    invoices = db.query(Invoice).filter(
        Invoice.school_id == student.school_id,
        Invoice.student_id == student.id,
    ).order_by(Invoice.id).all()
    items = [
        {
            "invoice_number": inv.invoice_number,
            "total": float(inv.total),
            "balance": float(invoice_balance(db, inv)),
            "currency": inv.currency,
            "issued_at": inv.issued_at.isoformat() if inv.issued_at else None,
        }
        for inv in invoices
    ]
    return {
        "student_number": student.student_number,
        "name": f"{student.first_name} {student.last_name}",
        "invoices": items,
        "total_balance": float(student_balance(db, student.school_id, student.id)),
    }


@router.get("/parent/children/{student_id}/report-card")
def parent_child_report_card(student_id: int, term_id: Optional[int] = None, principal: SupabasePrincipal = Depends(get_supabase_principal), db: Session = Depends(get_db)):
    student = _parent_student(principal, student_id, db)
    from app.models.results import Mark, Assessment, Subject
    q = db.query(Mark, Assessment, Subject).join(
        Assessment, Assessment.id == Mark.assessment_id
    ).join(
        Subject, Subject.id == Assessment.subject_id
    ).filter(
        Mark.school_id == student.school_id,
        Assessment.school_id == student.school_id,
        Subject.school_id == student.school_id,
        Mark.student_id == student.id,
        Mark.status == "published",
    )
    if term_id is not None:
        from app.models.fee import Term
        if db.query(Term).filter(Term.id == term_id, Term.school_id == student.school_id).first() is None:
            raise HTTPException(status_code=404, detail="Term not found in this school")
        q = q.filter(Assessment.term_id == term_id)
    subjects = {}
    for mark, assessment, subject in q.all():
        subjects.setdefault(subject.name, []).append(
            (assessment.name, float(mark.score), float(assessment.max_score), float(assessment.weight))
        )
    results = []
    for name, entries in subjects.items():
        total_weight = sum(weight for _, _, _, weight in entries)
        weighted = sum((score / maximum) * weight for _, score, maximum, weight in entries) if total_weight else 0
        results.append({
            "subject": name,
            "average": round(weighted / total_weight * 100, 2) if total_weight else 0,
            "assessments": [
                {"name": assessment_name, "score": score, "max": maximum}
                for assessment_name, score, maximum, _ in entries
            ],
        })
    return {
        "student_id": student.id,
        "student_number": student.student_number,
        "name": f"{student.first_name} {student.last_name}",
        "subjects": results,
    }

@router.post("/register", status_code=status.HTTP_410_GONE)
def portal_register():
    """Legacy local-password registration is disabled during Supabase migration."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Legacy registration is closed. Contact your school for a verified activation invitation.",
    )


@router.get("/fee-status")
def portal_fee_status(principal: SupabasePrincipal = Depends(get_supabase_principal), db: Session = Depends(get_db)):
    if principal.role != "student":
        raise HTTPException(status_code=403, detail="Portal users only")
    # Require one unambiguous, active learner mapping in the same school
    # tenant as the trusted Supabase profile.
    linked_students = db.query(Student).filter(
        Student.portal_user_id == principal.user_id,
        Student.school_id == principal.school_id,
    ).all()
    if len(linked_students) != 1:
        raise HTTPException(status_code=403, detail="Student account is not uniquely linked")
    student = linked_students[0]
    if student.status != "active":
        raise HTTPException(status_code=403, detail="Student account is inactive")
    invoices = db.query(Invoice).filter(Invoice.school_id == student.school_id, Invoice.student_id == student.id).order_by(Invoice.id).all()
    items = []
    for inv in invoices:
        bal = invoice_balance(db, inv)
        items.append({
            "invoice_number": inv.invoice_number,
            "total": float(inv.total),
            "balance": float(bal),
            "currency": inv.currency,
            "issued_at": inv.issued_at.isoformat() if inv.issued_at else None,
        })
    total_balance = student_balance(db, student.school_id, student.id)
    return {
        "student_number": student.student_number,
        "name": f"{student.first_name} {student.last_name}",
        "invoices": items,
        "total_balance": float(total_balance),
    }


@router.get("/me")
def portal_me(principal: SupabasePrincipal = Depends(get_supabase_principal), db: Session = Depends(get_db)):
    if principal.role != "student":
        raise HTTPException(status_code=403, detail="Student portal only")
    from app.models.user import User
    user = db.get(User, principal.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": principal.role, "school_id": principal.school_id}
