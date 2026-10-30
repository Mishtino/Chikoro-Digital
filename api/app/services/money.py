from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.payment import Invoice, Payment, PaymentAllocation


def to_decimal(value) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal("0")


def invoice_paid_amount(db: Session, invoice_id: int) -> Decimal:
    total = (
        db.query(func.coalesce(func.sum(PaymentAllocation.amount), 0))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .filter(PaymentAllocation.invoice_id == invoice_id)
        .filter(Payment.voided.is_(False))
        .scalar()
    )
    return to_decimal(total)


def invoice_balance(db: Session, invoice: Invoice) -> Decimal:
    return to_decimal(invoice.total) - invoice_paid_amount(db, invoice.id)


def student_balance(db: Session, school_id: int, student_id: int) -> Decimal:
    invoices = db.query(Invoice).filter(
        Invoice.school_id == school_id, Invoice.student_id == student_id, Invoice.status != "void"
    ).all()
    total_invoiced = sum((to_decimal(i.total) for i in invoices), Decimal("0"))
    paid = Decimal("0")
    for inv in invoices:
        paid += invoice_paid_amount(db, inv.id)
    return total_invoiced - paid


def allocate_payment(db: Session, payment: Payment, invoice_ids: list[int] | None = None) -> None:
    """Allocate a payment to invoices. If invoice_ids provided, allocate to those; else oldest open invoices first."""
    remaining = to_decimal(payment.amount)
    if invoice_ids:
        invoices = db.query(Invoice).filter(
            Invoice.id.in_(invoice_ids), Invoice.school_id == payment.school_id, Invoice.student_id == payment.student_id
        ).all()
    else:
        invoices = (
            db.query(Invoice)
            .filter(
                Invoice.school_id == payment.school_id,
                Invoice.student_id == payment.student_id,
                Invoice.status != "void",
            )
            .order_by(Invoice.issued_at.asc(), Invoice.id.asc())
            .all()
        )

    for inv in invoices:
        if remaining <= 0:
            break
        bal = invoice_balance(db, inv)
        if bal <= 0:
            continue
        alloc = min(bal, remaining)
        db.add(PaymentAllocation(school_id=payment.school_id, payment_id=payment.id, invoice_id=inv.id, amount=alloc))
        remaining -= alloc
    db.flush()
