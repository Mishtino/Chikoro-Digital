"""Test-only candidate finance policies; never imported by the production API.

Caller must enforce the loopback/explicit-opt-in guard and rollback fixture DDL.
These cover ordinary school finance reads, not portal access or financial writes.
"""
import re

from sqlalchemy import text


def install_finance_read_policies(connection, runtime_role):
    if not re.fullmatch(r"finance_rehearsal_[0-9a-f]{32}", runtime_role):
        raise ValueError("Generated local finance rehearsal role required")
    base = """school_id = NULLIF(current_setting('app.school_id',true),'')::int
        AND current_setting('app.role',true) IN ('owner','headmaster','bursar')
        AND NULLIF(current_setting('app.local_user_id',true),'') IS NOT NULL
        AND NULLIF(current_setting('request.jwt.claim.sub',true),'') IS NOT NULL
        AND current_setting('app.is_platform_admin',true) = 'false'
        AND current_setting('app.request_kind',true) = 'ordinary'"""
    predicates = {
        "students": base,
        "invoices": base + """ AND EXISTS (SELECT 1 FROM public.students s
            WHERE s.id=invoices.student_id AND s.school_id=invoices.school_id)""",
        "payments": base + """ AND EXISTS (SELECT 1 FROM public.students s
            WHERE s.id=payments.student_id AND s.school_id=payments.school_id)""",
        "invoice_lines": base + """ AND EXISTS (SELECT 1 FROM public.invoices i
            WHERE i.id=invoice_lines.invoice_id AND i.school_id=invoice_lines.school_id)""",
        "payment_allocations": base + """ AND EXISTS (
            SELECT 1 FROM public.payments p JOIN public.invoices i
                ON i.id=payment_allocations.invoice_id
            WHERE p.id=payment_allocations.payment_id
                AND p.school_id=payment_allocations.school_id
                AND i.school_id=payment_allocations.school_id
                AND p.student_id=i.student_id AND p.currency=i.currency)""",
        "receipts": base + """ AND EXISTS (SELECT 1 FROM public.payments p
            WHERE p.id=receipts.payment_id AND p.school_id=receipts.school_id)""",
    }
    for table, predicate in predicates.items():
        connection.execute(text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
        columns = " (id,school_id)" if table == "students" else ""
        connection.execute(text(f"GRANT SELECT{columns} ON public.{table} TO {runtime_role}"))
        connection.execute(text(f"CREATE POLICY finance_read ON public.{table} FOR SELECT TO {runtime_role} USING ({predicate})"))
