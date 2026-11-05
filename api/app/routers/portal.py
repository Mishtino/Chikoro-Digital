from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy import text

from app.database import get_db
from app.deps_supabase import get_supabase_principal, SupabasePrincipal
from app.models.student import Student, Contact
from app.models.attendance import AttendanceSession, AttendanceRecord
from app.models.payment import Invoice
from app.services.money import invoice_balance

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


def _student_portal_student(principal: SupabasePrincipal, db: Session) -> Student:
    """Resolve exactly one learner record, including inactive historical mappings."""
    if principal.role != "student":
        raise HTTPException(status_code=403, detail="Student portal only")
    if principal.school_id is None:
        raise HTTPException(status_code=403, detail="School context required")
    linked_students = db.query(Student).filter(
        Student.portal_user_id == principal.user_id,
        Student.school_id == principal.school_id,
    ).all()
    if len(linked_students) != 1:
        raise HTTPException(status_code=403, detail="Student account is not uniquely linked")
    student = linked_students[0]
    if student.status != "active":
        raise HTTPException(status_code=403, detail="Student account is inactive")
    return student


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
        Invoice.status != "void",
    ).order_by(Invoice.id).all()
    balances_by_currency = {}
    for invoice in invoices:
        balances_by_currency[invoice.currency] = balances_by_currency.get(invoice.currency, 0.0) + float(invoice_balance(db, invoice))
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
        "total_balance": balances_by_currency.get("USD", 0.0),
        "balances_by_currency": balances_by_currency,
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
        subjects.setdefault(subject.id, {"name": subject.name, "entries": []})["entries"].append(
            (assessment.name, float(mark.score), float(assessment.max_score), float(assessment.weight))
        )
    results = []
    for subject_id, group in subjects.items():
        entries = group["entries"]
        total_weight = sum(weight for _, _, _, weight in entries)
        weighted = sum((score / maximum) * weight for _, score, maximum, weight in entries) if total_weight else 0
        results.append({
            "subject_id": subject_id,
            "subject": group["name"],
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

@router.get("/parent/children/{student_id}/terms")
def parent_child_terms(student_id: int, principal: SupabasePrincipal = Depends(get_supabase_principal), db: Session = Depends(get_db)):
    """Return only terms with published marks for this verified linked learner."""
    student = _parent_student(principal, student_id, db)
    from app.models.results import Mark, Assessment
    from app.models.fee import Term

    terms = db.query(Term).join(
        Assessment, Assessment.term_id == Term.id
    ).join(
        Mark, Mark.assessment_id == Assessment.id
    ).filter(
        Term.school_id == student.school_id,
        Assessment.school_id == student.school_id,
        Mark.school_id == student.school_id,
        Mark.student_id == student.id,
        Mark.status == "published",
    ).distinct().order_by(
        Term.academic_year.desc(), Term.start_date.desc(), Term.id.desc()
    ).all()
    return {
        "terms": [
            {"id": term.id, "name": term.name, "academic_year": term.academic_year,
             "is_current": bool(term.is_current)}
            for term in terms
        ]
    }




@router.get("/parent/children/{student_id}/attendance")
def parent_child_attendance(
    student_id: int,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    """Return submitted attendance only for a verified, linked learner."""
    student = _parent_student(principal, student_id, db)
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=422, detail="from_date must be on or before to_date")

    query = db.query(AttendanceRecord, AttendanceSession).join(
        AttendanceSession,
        (AttendanceSession.id == AttendanceRecord.session_id)
        & (AttendanceSession.school_id == AttendanceRecord.school_id),
    ).filter(
        AttendanceRecord.school_id == student.school_id,
        AttendanceRecord.student_id == student.id,
        AttendanceSession.school_id == student.school_id,
        AttendanceSession.status == "submitted",
    )
    if from_date:
        query = query.filter(AttendanceSession.attendance_date >= from_date)
    if to_date:
        query = query.filter(AttendanceSession.attendance_date <= to_date)

    grouped_counts = db.query(
        AttendanceRecord.status, func.count(AttendanceRecord.id)
    ).join(
        AttendanceSession,
        (AttendanceSession.id == AttendanceRecord.session_id)
        & (AttendanceSession.school_id == AttendanceRecord.school_id),
    ).filter(
        AttendanceRecord.school_id == student.school_id,
        AttendanceRecord.student_id == student.id,
        AttendanceSession.school_id == student.school_id,
        AttendanceSession.status == "submitted",
    )
    if from_date:
        grouped_counts = grouped_counts.filter(AttendanceSession.attendance_date >= from_date)
    if to_date:
        grouped_counts = grouped_counts.filter(AttendanceSession.attendance_date <= to_date)
    grouped_counts = grouped_counts.group_by(AttendanceRecord.status).all()
    counts = {"present": 0, "absent": 0, "late": 0, "excused": 0}
    for state, count in grouped_counts:
        if state in counts:
            counts[state] = count
    total = sum(counts.values())

    rows = query.order_by(
        AttendanceSession.attendance_date.desc(),
        AttendanceSession.id.desc(),
    ).limit(100).all()
    records = []
    for record, session in rows:
        records.append({
            "date": session.attendance_date.isoformat(),
            "class_name": session.class_name,
            "status": record.status,
            "note": record.note,
        })
    return {
        "student_id": student.id,
        "student_number": student.student_number,
        "name": f"{student.first_name} {student.last_name}",
        "summary": {
            "total_recorded_days": total,
            "present": counts["present"],
            "absent": counts["absent"],
            "late": counts["late"],
            "excused": counts["excused"],
            "attendance_rate": round(
                (counts["present"] + counts["late"]) / total * 100, 1
            ) if total else None,
        },
        "records": records,
        "records_limited": total > len(records),
    }


def _term_comparison_payload(student: Student, selected_term_id: Optional[int], db: Session):
    """Compare a learner's selected published-results term with the preceding published term."""
    from app.models.results import Mark, Assessment, Subject
    from app.models.fee import Term

    terms = db.query(Term).join(
        Assessment, Assessment.term_id == Term.id
    ).join(
        Mark, Mark.assessment_id == Assessment.id
    ).filter(
        Term.school_id == student.school_id,
        Assessment.school_id == student.school_id,
        Mark.school_id == student.school_id,
        Mark.student_id == student.id,
        Mark.status == "published",
    ).distinct().order_by(
        Term.academic_year.desc(), Term.start_date.desc(), Term.id.desc()
    ).all()
    if not terms:
        return {"current_term": None, "previous_term": None, "subjects": []}
    selected_index = 0
    if selected_term_id is not None:
        selected_index = next((i for i, term in enumerate(terms) if term.id == selected_term_id), -1)
        if selected_index < 0:
            raise HTTPException(status_code=404, detail="Term not found in this learner's published results")
    current = terms[selected_index]
    previous = terms[selected_index + 1] if selected_index + 1 < len(terms) else None

    def averages(term):
        if term is None:
            return {}
        rows = db.query(
            Subject.id, Subject.name,
            func.sum((Mark.score / Assessment.max_score) * Assessment.weight).label("weighted_score"),
            func.sum(Assessment.weight).label("total_weight"),
        ).join(
            Assessment, Assessment.subject_id == Subject.id
        ).join(
            Mark, Mark.assessment_id == Assessment.id
        ).filter(
            Subject.school_id == student.school_id,
            Assessment.school_id == student.school_id,
            Mark.school_id == student.school_id,
            Mark.student_id == student.id,
            Assessment.term_id == term.id,
            Mark.status == "published",
        ).group_by(Subject.id, Subject.name).all()
        return {
            row.id: {
                "subject_id": row.id,
                "subject": row.name,
                "average": round(float(row.weighted_score or 0) / float(row.total_weight or 1) * 100, 2),
            }
            for row in rows
        }

    current_rows = averages(current)
    previous_rows = averages(previous)
    subjects = []
    for subject_id in sorted(set(current_rows) | set(previous_rows)):
        now = current_rows.get(subject_id)
        before = previous_rows.get(subject_id)
        subjects.append({
            "subject_id": subject_id,
            "subject": (now or before)["subject"],
            "current_average": now["average"] if now else None,
            "previous_average": before["average"] if before else None,
            "change": round(now["average"] - before["average"], 2) if now and before else None,
        })
    return {
        "current_term": {"id": current.id, "name": current.name, "academic_year": current.academic_year},
        "previous_term": {"id": previous.id, "name": previous.name, "academic_year": previous.academic_year} if previous else None,
        "subjects": subjects,
    }


@router.get("/results/comparison")
def student_term_comparison(
    term_id: Optional[int] = None,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    student = _student_portal_student(principal, db)
    return _term_comparison_payload(student, term_id, db)


@router.get("/parent/children/{student_id}/results/comparison")
def parent_child_term_comparison(
    student_id: int,
    term_id: Optional[int] = None,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    student = _parent_student(principal, student_id, db)
    return _term_comparison_payload(student, term_id, db)


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
    student = _student_portal_student(principal, db)
    invoices = db.query(Invoice).filter(Invoice.school_id == student.school_id, Invoice.student_id == student.id, Invoice.status != "void").order_by(Invoice.id).all()
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
    balances_by_currency = {}
    for invoice in invoices:
        balances_by_currency[invoice.currency] = balances_by_currency.get(invoice.currency, 0.0) + float(invoice_balance(db, invoice))
    total_balance = balances_by_currency.get("USD", 0.0)
    return {
        "student_number": student.student_number,
        "name": f"{student.first_name} {student.last_name}",
        "invoices": items,
        "total_balance": float(total_balance),
        "balances_by_currency": balances_by_currency,
    }


@router.get("/terms")
def student_published_terms(principal: SupabasePrincipal = Depends(get_supabase_principal), db: Session = Depends(get_db)):
    """Return academic terms containing published marks for the authenticated learner only."""
    student = _student_portal_student(principal, db)
    from app.models.results import Mark, Assessment
    from app.models.fee import Term

    terms = db.query(Term).join(
        Assessment, Assessment.term_id == Term.id
    ).join(
        Mark, Mark.assessment_id == Assessment.id
    ).filter(
        Term.school_id == student.school_id,
        Assessment.school_id == student.school_id,
        Mark.school_id == student.school_id,
        Mark.student_id == student.id,
        Mark.status == "published",
    ).distinct().order_by(
        Term.academic_year.desc(), Term.start_date.desc(), Term.id.desc()
    ).all()
    return {"terms": [
        {"id": term.id, "name": term.name, "academic_year": term.academic_year,
         "is_current": bool(term.is_current)}
        for term in terms
    ]}


@router.get("/results")
def portal_results(term_id: Optional[int] = None, principal: SupabasePrincipal = Depends(get_supabase_principal), db: Session = Depends(get_db)):
    student = _student_portal_student(principal, db)
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
        subjects.setdefault(subject.id, {"name": subject.name, "entries": []})["entries"].append(
            (assessment.name, float(mark.score), float(assessment.max_score), float(assessment.weight))
        )
    results = []
    for subject_id, group in subjects.items():
        entries = group["entries"]
        total_weight = sum(weight for _, _, _, weight in entries)
        weighted = sum((score / maximum) * weight for _, score, maximum, weight in entries) if total_weight else 0
        results.append({
            "subject_id": subject_id,
            "subject": group["name"],
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


@router.get("/me")
def portal_me(principal: SupabasePrincipal = Depends(get_supabase_principal), db: Session = Depends(get_db)):
    if principal.role != "student":
        raise HTTPException(status_code=403, detail="Student portal only")
    from app.models.user import User
    user = db.get(User, principal.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": principal.role, "school_id": principal.school_id}
