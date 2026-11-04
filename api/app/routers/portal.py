from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps_supabase import get_supabase_principal, SupabasePrincipal
from app.models.student import Student
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
    from app.models.user import User
    # find student linked to this user
    student = db.query(Student).filter(Student.portal_user_id == principal.user_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail="No student linked to this account")
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
    from app.models.user import User
    user = db.get(User, principal.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": principal.role, "school_id": principal.school_id}
