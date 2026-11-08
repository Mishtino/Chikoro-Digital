"""Real manual-payment/void route assertions for the guarded local rehearsal."""
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.services.tenant_identity import resolve_tenant_identity
from app.tenant_context import TenantContextSession
from staging_finance_write_policies import install_finance_write_policies


def exercise_finance_writes(connection, role, client):
    connection.execute(text('RESET ROLE'))
    install_finance_write_policies(connection,role)
    connection.execute(text(f'SET LOCAL ROLE {role}'))

    def snapshot():
        connection.execute(text('RESET ROLE'))
        try:
            return tuple(connection.scalar(text(f'SELECT count(*) FROM public.{t}'))
                for t in ('payments','payment_allocations','receipts','audit_logs'))
        finally:
            connection.execute(text(f'SET LOCAL ROLE {role}'))

    def headers(uid):
        return {'Authorization':f'Bearer {uid}'}

    def post(uid,payload):
        return client.post('/payments',headers=headers(uid),json=payload)

    initial=snapshot()
    created={}
    for uid in (1,3,4,2):
        response=post(uid,{'student_id':3 if uid==2 else 1,'amount':15 if uid==2 else 10,
            'method':'cash','reference':f'MANUAL-{uid}','invoice_ids':[3 if uid==2 else 1]})
        assert response.status_code==201,response.text
        created[uid]=response.json()['payment_id']
        assert response.json()['receipt_number'].startswith('RCP-')
    assert snapshot()==tuple(n+4 for n in initial)

    def balance(uid,invoice):
        response=client.get(f'/invoices/{invoice}',headers=headers(uid))
        assert response.status_code==200,response.text
        return response.json()['balance']
    assert balance(1,1)==40 and balance(2,3)==165
    before=snapshot()
    invalid=(
        (1,{'student_id':3,'amount':1,'method':'cash'},404),
        (1,{'student_id':1,'school_id':2,'amount':1,'method':'cash'},403),
        (1,{'student_id':2,'invoice_ids':[1],'amount':1,'method':'cash'},404),
        (1,{'student_id':1,'amount':1000,'method':'cash'},422),
        (1,{'student_id':1,'amount':1,'method':' '},422),
        (1,{'student_id':1,'amount':1,'method':'paynow'},422),
        (1,{'student_id':1,'amount':1,'method':'cash','reference':'MANUAL-1'},409),
    )
    for uid,payload,status in invalid:
        response=post(uid,payload)
        assert response.status_code==status,(payload,response.status_code,response.text)
    for uid in (5,6,7,8,9):
        assert post(uid,{'student_id':1,'amount':1,'method':'cash'}).status_code==403
    assert snapshot()==before,'Rejected API requests created partial finance/audit records'

    # Distinct bad writes prove policy checks, not primary-key collisions.
    with TenantContextSession(bind=connection,join_transaction_mode='create_savepoint') as db:
        resolve_tenant_identity(db,'1')
        denied=(
            "INSERT INTO public.payments (school_id,student_id,amount,currency,method,received_by_user_id,voided) VALUES (2,3,1,'USD','cash',1,false)",
            "INSERT INTO public.payments (school_id,student_id,amount,currency,method,received_by_user_id,voided) VALUES (1,3,1,'USD','cash',1,false)",
            "INSERT INTO public.payments (school_id,student_id,amount,currency,method,received_by_user_id,voided) VALUES (1,1,1,'USD','paynow',1,false)",
            f"INSERT INTO public.payment_allocations (school_id,payment_id,invoice_id,amount) VALUES (1,{created[1]},2,1)",
            f"INSERT INTO public.receipts (school_id,payment_id,receipt_number) VALUES (1,{created[2]},'RCP-99999')",
            f"INSERT INTO public.audit_logs (school_id,actor_user_id,action,entity_type,entity_id) VALUES (1,3,'payment.record','payment','{created[1]}')",
            f"INSERT INTO public.audit_logs (school_id,actor_user_id,action,entity_type,entity_id) VALUES (2,1,'payment.record','payment','{created[1]}')",
            'UPDATE public.payments SET amount=999 WHERE school_id=1',
            'DELETE FROM public.payments WHERE school_id=1',
            'UPDATE public.schools SET id=id WHERE id=1',
            'UPDATE public.invoices SET id=id WHERE id=1',
            'SELECT paynow_integration_key FROM public.schools',
            'SELECT activation_pin_hash FROM public.students',
            'DELETE FROM public.audit_logs',
            "UPDATE public.audit_logs SET action='tampered'",
        )
        for statement in denied:
            try:
                db.execute(text(statement))
            except DBAPIError as exc:
                assert exc.orig.sqlstate=='42501',(statement,str(exc.orig))
                db.rollback()
            else:
                raise AssertionError('Restricted role accepted forbidden write/read: '+statement)
    assert snapshot()==before,'Rejected raw writes left partial records'

    # Bursars can record but cannot void. Owners/headmasters retain school scope.
    assert client.post(f'/payments/{created[4]}/void',headers=headers(4),json={'reason':'no'}).status_code==403
    assert client.post(f'/payments/{created[2]}/void',headers=headers(1),json={'reason':'wrong school'}).status_code==404
    assert snapshot()==before
    for uid,payment in ((1,created[4]),(3,created[1]),(2,created[2])):
        response=client.post(f'/payments/{payment}/void',headers=headers(uid),json={'reason':'Rehearsal correction'})
        assert response.status_code==200,response.text
    assert client.post(f'/payments/{created[4]}/void',headers=headers(1),json={'reason':'again'}).status_code==400
    assert balance(1,1)==60 and balance(2,3)==180
    assert snapshot()==(before[0],before[1],before[2],before[3]+3)
    # Inspect append-only evidence as fixture owner, outside API request context.
    connection.execute(text('RESET ROLE'))
    try:
        events=connection.execute(text("SELECT actor_user_id,action,school_id,entity_id FROM public.audit_logs ORDER BY id")).all()
        assert len(events)==7
        assert {(r[0],r[1],r[2],r[3]) for r in events}=={
            *((uid,'payment.record',2 if uid==2 else 1,str(pid)) for uid,pid in created.items()),
            (1,'payment.void',1,str(created[4])),(3,'payment.void',1,str(created[1])),(2,'payment.void',2,str(created[2]))}
    finally:
        connection.execute(text(f'SET LOCAL ROLE {role}'))
    print('PASS: manual payment recording, own-school locks, allocations, receipts, sequence grants, owner/headmaster voids and append-only actor-bound audits; rejected API/raw writes leave no partial records')
