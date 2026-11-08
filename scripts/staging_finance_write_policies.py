"""Local rehearsal-only manual finance write candidates, not a migration."""
import re
from sqlalchemy import text


def install_finance_write_policies(connection, role):
    if not re.fullmatch(r"finance_rehearsal_[0-9a-f]{32}", role):
        raise ValueError("Generated local finance rehearsal role required")
    base = """school_id=NULLIF(current_setting('app.school_id',true),'')::int
        AND current_setting('app.role',true) IN ('owner','headmaster','bursar')
        AND NULLIF(current_setting('request.jwt.claim.sub',true),'') IS NOT NULL
        AND NULLIF(current_setting('app.local_user_id',true),'') IS NOT NULL
        AND current_setting('app.request_kind',true)='ordinary'
        AND current_setting('app.is_platform_admin',true)='false'"""
    actor = "NULLIF(current_setting('app.local_user_id',true),'')::int"
    connection.execute(text("ALTER TABLE public.schools ENABLE ROW LEVEL SECURITY"))
    school_scope = base.replace('school_id=', 'id=', 1)
    connection.execute(text(f"GRANT SELECT (id),UPDATE (id) ON public.schools TO {role}"))
    connection.execute(text(f"CREATE POLICY finance_lock_read ON public.schools FOR SELECT TO {role} USING ({school_scope})"))
    # Row-lock privileges do not authorize actual school or invoice mutations.
    for table, scope in (('schools',school_scope),('invoices',base)):
        connection.execute(text(f"GRANT UPDATE (id) ON public.{table} TO {role}"))
        connection.execute(text(f"CREATE POLICY finance_lock ON public.{table} FOR UPDATE TO {role} USING ({scope}) WITH CHECK (false)"))
    payment_student = """EXISTS (SELECT 1 FROM public.students s
        WHERE s.id=payments.student_id AND s.school_id=payments.school_id)"""
    inserts = {
        'payments': ("school_id,student_id,amount,currency,method,reference,received_by_user_id,received_at,voided,voided_at,void_reason",
            base + f""" AND {payment_student} AND received_by_user_id={actor}
            AND amount>0 AND currency ~ '^[A-Z]{{3}}$'
            AND length(trim(method))>0 AND lower(trim(method))<>'paynow'
            AND (reference IS NULL OR lower(reference) NOT LIKE 'paynow:%')
            AND NOT voided AND voided_at IS NULL AND void_reason IS NULL"""),
        'payment_allocations': ("school_id,payment_id,invoice_id,amount",
            base + f""" AND amount>0 AND EXISTS (
            SELECT 1 FROM public.payments p JOIN public.invoices i ON i.id=payment_allocations.invoice_id
            WHERE p.id=payment_allocations.payment_id
              AND p.school_id=payment_allocations.school_id AND i.school_id=payment_allocations.school_id
              AND p.student_id=i.student_id AND p.currency=i.currency
              AND NOT p.voided AND i.status<>'void' AND p.received_by_user_id={actor})"""),
        'receipts': ("school_id,payment_id,receipt_number,issued_at",
            base + f""" AND receipt_number ~ '^RCP-[0-9]{{5,}}$' AND EXISTS (
            SELECT 1 FROM public.payments p WHERE p.id=receipts.payment_id
              AND p.school_id=receipts.school_id AND NOT p.voided AND p.received_by_user_id={actor})"""),
    }
    for table,(columns,check) in inserts.items():
        connection.execute(text(f"GRANT INSERT ({columns}) ON public.{table} TO {role}"))
        connection.execute(text(f"CREATE POLICY manual_finance_insert ON public.{table} FOR INSERT TO {role} WITH CHECK ({check})"))
    void_scope = base + f" AND current_setting('app.role',true) IN ('owner','headmaster') AND {payment_student}"
    connection.execute(text(f"GRANT UPDATE (voided,voided_at,void_reason) ON public.payments TO {role}"))
    connection.execute(text(f"""CREATE POLICY manual_payment_void ON public.payments FOR UPDATE TO {role}
        USING ({void_scope}) WITH CHECK ({void_scope} AND voided AND voided_at IS NOT NULL
            AND void_reason IS NOT NULL AND length(trim(void_reason))>0)"""))
    connection.execute(text("ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY"))
    audit_scope=base + f" AND actor_user_id={actor}"
    connection.execute(text(f"GRANT SELECT (id), INSERT (school_id,actor_user_id,action,entity_type,entity_id,details,created_at) ON public.audit_logs TO {role}"))
    connection.execute(text(f"CREATE POLICY own_finance_audit_read ON public.audit_logs FOR SELECT TO {role} USING ({audit_scope})"))
    connection.execute(text(f"""CREATE POLICY manual_finance_audit ON public.audit_logs FOR INSERT TO {role}
        WITH CHECK ({audit_scope} AND entity_type='payment' AND EXISTS (
            SELECT 1 FROM public.payments p WHERE entity_id=p.id::text AND p.school_id=audit_logs.school_id
              AND ((action='payment.record' AND NOT p.voided AND p.received_by_user_id={actor})
                OR (action='payment.void' AND p.voided AND current_setting('app.role',true) IN ('owner','headmaster')))))"""))
    for table in ('payments','payment_allocations','receipts','audit_logs'):
        # RESTART is transactional, unlike setval; fixture rollback restores it.
        connection.execute(text(f"ALTER SEQUENCE public.{table}_id_seq RESTART WITH 1000"))
        connection.execute(text(f"GRANT USAGE ON SEQUENCE public.{table}_id_seq TO {role}"))
