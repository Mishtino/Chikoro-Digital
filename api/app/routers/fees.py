from datetime import date
import math
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps_supabase import SupabasePrincipal, require_supabase_roles
from app.models.fee import Term, FeeItem, FeeStructure, FeeStructureItem
from app.models.payment import Invoice, InvoiceLine
from app.models.student import Student
from app.models.school import School
from app.services.audit import write_audit

router = APIRouter(prefix="/fees", tags=["fees"])


class TermCreate(BaseModel):
    name: str
    academic_year: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_current: bool = False
    school_id: Optional[int] = None


class TermOut(BaseModel):
    id: int
    school_id: int
    name: str
    academic_year: str
    is_current: bool

    class Config:
        from_attributes = True


class FeeItemCreate(BaseModel):
    name: str
    amount: float
    currency: str = "USD"
    applies_to_form: Optional[str] = None
    school_id: Optional[int] = None


class FeeItemOut(BaseModel):
    id: int
    school_id: int
    name: str
    amount: float
    currency: str
    applies_to_form: Optional[str] = None

    class Config:
        from_attributes = True
class FeeStructureCreate(BaseModel):
    term_id: int
    form: Optional[str] = None
    name: str
    items: List[dict]
    school_id: Optional[int] = None


class GenerateInvoicesRequest(BaseModel):
    term_id: int
    form: Optional[str] = None
    school_id: Optional[int] = None


def _sid(principal: SupabasePrincipal, requested: Optional[int]) -> int:
    if principal.is_admin:
        if requested is None:
            raise HTTPException(status_code=400, detail="school_id required")
        return requested
    if principal.school_id is None:
        raise HTTPException(status_code=403, detail="School context required")
    return principal.school_id


@router.post("/terms", response_model=TermOut, status_code=status.HTTP_201_CREATED)
def create_term(payload: TermCreate, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar')), db: Session = Depends(get_db)):
    sid = _sid(principal, payload.school_id)
    if payload.is_current:
        db.query(Term).filter(Term.school_id == sid).update({"is_current": False})
    term = Term(school_id=sid, name=payload.name, academic_year=payload.academic_year, start_date=payload.start_date, end_date=payload.end_date, is_current=payload.is_current)
    db.add(term)
    db.commit()
    db.refresh(term)
    write_audit(db, principal, "term.create", "term", term.id, {"name": term.name}, school_id=sid)
    return term


@router.get("/terms", response_model=List[TermOut])
def list_terms(school_id: Optional[int] = Query(None), principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar')), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id) if (principal.is_admin or school_id is not None) else principal.school_id
    if sid is None:
        raise HTTPException(status_code=403, detail="School context required")
    return db.query(Term).filter(Term.school_id == sid).order_by(Term.id).all()


@router.post("/fee-items", response_model=FeeItemOut, status_code=status.HTTP_201_CREATED)
def create_fee_item(payload: FeeItemCreate, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar')), db: Session = Depends(get_db)):
    sid = _sid(principal, payload.school_id)
    if not math.isfinite(payload.amount) or payload.amount <= 0:
        raise HTTPException(status_code=422, detail="Fee amount must be a finite positive value")
    currency = payload.currency.upper()
    if len(currency) != 3 or not currency.isalpha():
        raise HTTPException(status_code=422, detail="Currency must be a three-letter code")
    item = FeeItem(school_id=sid, name=payload.name, amount=payload.amount, currency=currency, applies_to_form=payload.applies_to_form)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/fee-items", response_model=List[FeeItemOut])
def list_fee_items(school_id: Optional[int] = Query(None), principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar')), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id) if (principal.is_admin or school_id is not None) else principal.school_id
    if sid is None:
        raise HTTPException(status_code=403, detail="School context required")
    return db.query(FeeItem).filter(FeeItem.school_id == sid).order_by(FeeItem.id).all()


@router.post("/fee-structures", status_code=status.HTTP_201_CREATED)
def create_fee_structure(payload: FeeStructureCreate, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar')), db: Session = Depends(get_db)):
    sid = _sid(principal, payload.school_id)
    if db.query(Term).filter(Term.id == payload.term_id, Term.school_id == sid).first() is None:
        raise HTTPException(status_code=404, detail="Term not found in this school")
    if not payload.items:
        raise HTTPException(status_code=422, detail="At least one fee item is required")
    currencies = set()
    for item in payload.items:
        item_currency = str(item.get("currency", "USD")).upper()
        if len(item_currency) != 3 or not item_currency.isalpha():
            raise HTTPException(status_code=422, detail="Fee currency must be a three-letter code")
        currencies.add(item_currency)
        try:
            item_amount = float(item.get("amount", 0))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Fee amounts must be valid numbers")
        if not math.isfinite(item_amount) or item_amount <= 0:
            raise HTTPException(status_code=422, detail="Fee amounts must be finite positive values")
        fee_item_id = item.get("fee_item_id")
        if fee_item_id is not None:
            fee_item = db.query(FeeItem).filter(FeeItem.id == fee_item_id, FeeItem.school_id == sid).first()
            if fee_item is None:
                raise HTTPException(status_code=404, detail="Fee item not found in this school")
            if fee_item.currency.upper() != item_currency:
                raise HTTPException(status_code=422, detail="Fee structure item currency must match its fee item")
    if len(currencies) != 1:
        raise HTTPException(status_code=422, detail="A fee structure must use one currency")
    fs = FeeStructure(school_id=sid, term_id=payload.term_id, form=payload.form, name=payload.name)
    db.add(fs)
    db.flush()
    for it in payload.items:
        line = FeeStructureItem(
            school_id=sid,
            fee_structure_id=fs.id,
            fee_item_id=it.get("fee_item_id"),
            description=it.get("description", "Fee"),
            amount=it["amount"],
            currency=str(it.get("currency", "USD")).upper(),
        )
        db.add(line)
    db.commit()
    db.refresh(fs)
    write_audit(db, principal, "fee_structure.create", "fee_structure", fs.id, {"name": fs.name}, school_id=sid)
    return {"id": fs.id}


@router.post("/invoices/generate")
def generate_invoices(payload: GenerateInvoicesRequest, principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster', 'bursar')), db: Session = Depends(get_db)):
    sid = _sid(principal, payload.school_id)
    term = db.get(Term, payload.term_id)
    if term is None or term.school_id != sid:
        raise HTTPException(status_code=404, detail="Term not found")
    fs_query = db.query(FeeStructure).filter(FeeStructure.school_id == sid, FeeStructure.term_id == payload.term_id)
    if payload.form:
        fs_query = fs_query.filter(FeeStructure.form == payload.form)
    fee_structure = fs_query.first()
    if fee_structure is None:
        raise HTTPException(status_code=404, detail="Fee structure not found for term/form")

    items = db.query(FeeStructureItem).filter(FeeStructureItem.fee_structure_id == fee_structure.id).all()
    total = sum(float(i.amount) for i in items)
    currency = items[0].currency if items else "USD"

    q = db.query(Student).filter(Student.school_id == sid, Student.status == "active")
    if payload.form:
        q = q.filter(Student.form == payload.form)
    students = q.all()

    created = 0
    for st in students:
        exists = db.query(Invoice).filter(Invoice.school_id == sid, Invoice.student_id == st.id, Invoice.term_id == term.id).first()
        if exists:
            continue
        count = db.query(Invoice).filter(Invoice.school_id == sid).count()
        inv_number = f"INV-{count + 1:05d}"
        inv = Invoice(school_id=sid, student_id=st.id, term_id=term.id, invoice_number=inv_number, currency=currency, total=total)
        db.add(inv)
        db.flush()
        for it in items:
            db.add(InvoiceLine(school_id=sid, invoice_id=inv.id, description=it.description or "Fee", amount=it.amount))
        created += 1
    db.commit()
    write_audit(db, principal, "invoices.generate", "term", term.id, {"created": created, "form": payload.form}, school_id=sid)
    return {"created": created}

