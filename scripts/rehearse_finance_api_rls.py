"""Rollback-only finance API/RLS rehearsal using synthetic local financial data.

Run after the guarded financial migration rehearsal. Never target cloud DBs.
Token crypto is mocked at the existing verifier boundary, not profile resolution.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from local_db_guard import validate_database_url
from staging_finance_read_policies import install_finance_read_policies


def run():
    url = os.environ.get("DATABASE_URL", "")
    allowed, reason = validate_database_url(url)
    if not allowed:
        raise RuntimeError(f"Unsafe finance API rehearsal target: {reason}")
    if os.environ.get("CHIKORO_REHEARSAL_FINANCE_API") != "yes":
        raise RuntimeError("Explicit CHIKORO_REHEARSAL_FINANCE_API=yes required")
    driver_url = "postgresql+psycopg" + url[url.index(":"):]
    # App imports must use the same validated driver/target, never a .env URL.
    os.environ["DATABASE_URL"] = driver_url
    os.environ["ENV"] = "test"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
    from fastapi import Depends, FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from app.database import get_db, engine as unused_app_engine
    from app.deps_supabase import bearer, get_supabase_principal, SupabasePrincipal
    from app.routers.payments import router, invoices_router
    from app.services.tenant_identity import resolve_tenant_identity
    from app.tenant_context import TenantContextSession

    engine = create_engine(driver_url)
    role = "finance_rehearsal_" + uuid4().hex
    try:
        with engine.connect() as connection:
            outer = connection.begin()
            try:
                if connection.scalar(text("SELECT to_regclass('public.profiles')")) is not None:
                    raise RuntimeError("Refusing an existing profile database")
                if connection.scalar(text("SELECT count(*) FROM public.users")) != 0:
                    raise RuntimeError("Expected only synthetic financial rehearsal fixtures")
                assert connection.scalar(text("SELECT count(*) FROM public.schools")) == 2
                assert connection.scalar(text("SELECT count(*) FROM public.invoices")) == 3
                connection.execute(text("""CREATE TABLE public.profiles (
                    id uuid PRIMARY KEY, local_user_id int UNIQUE REFERENCES public.users(id),
                    role text NOT NULL, school_id int, is_active boolean NOT NULL)"""))
                identities = [(1,'owner',1),(2,'owner',2),(3,'headmaster',1),
                    (4,'bursar',1),(5,'teacher',1),(6,'student',1),(7,'parent',1),
                    (8,'vortex_admin',None),(9,'vortex_support',None)]
                for uid, profile_role, school in identities:
                    connection.execute(text("""INSERT INTO public.users
                        (id,email,password_hash,full_name,role,school_id,is_admin)
                        VALUES (:id,:email,'synthetic','Fixture',:role,:school,:admin)"""),
                        {"id":uid,"email":f"fixture{uid}@example.invalid", "role":'admin' if uid==8 else profile_role,
                         "school":school,"admin":uid==8})
                    connection.execute(text("INSERT INTO public.profiles VALUES (:id,:local,:role,:school,true)"),
                        {"id":UUID(int=uid),"local":uid,"role":profile_role,"school":school})
                connection.execute(text("UPDATE public.invoices SET total=CASE id WHEN 1 THEN 100 WHEN 2 THEN 80 ELSE 200 END"))
                connection.execute(text("UPDATE public.payment_allocations SET amount=30 WHERE id=10"))
                connection.execute(text("INSERT INTO public.payment_allocations VALUES (20,2,2,3,20),(90,1,1,2,5)"))
                connection.execute(text("""INSERT INTO public.invoices (id,school_id,student_id,invoice_number,total)
                    VALUES (90,1,3,'BAD-STUDENT',999)"""))
                connection.execute(text("""INSERT INTO public.payments (id,school_id,student_id,amount)
                    VALUES (90,1,3,999)"""))
                connection.execute(text("""INSERT INTO public.invoice_lines VALUES
                    (1,1,1,'School One',100),(2,2,3,'School Two',200),(90,1,3,'BAD-TENANT',999)"""))
                connection.execute(text("""INSERT INTO public.receipts (id,school_id,payment_id,receipt_number)
                    VALUES (1,1,1,'RCP-1'),(2,2,2,'RCP-2'),(90,1,2,'BAD-PAYMENT')"""))
                connection.execute(text(f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT"))
                connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
                connection.execute(text(f"GRANT SELECT (id,local_user_id,role,school_id,is_active) ON public.profiles TO {role}"))
                connection.execute(text(f"GRANT SELECT (id,role,school_id,is_admin,is_active) ON public.users TO {role}"))
                for table in ('profiles','users'):
                    connection.execute(text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
                connection.execute(text(f"""CREATE POLICY identity_profile ON public.profiles FOR SELECT TO {role}
                    USING (id=NULLIF(current_setting('request.jwt.claim.sub',true),'')::uuid)"""))
                connection.execute(text(f"""CREATE POLICY identity_user ON public.users FOR SELECT TO {role}
                    USING (EXISTS (SELECT 1 FROM public.profiles p WHERE p.local_user_id=users.id
                    AND p.id=NULLIF(current_setting('request.jwt.claim.sub',true),'')::uuid))"""))
                install_finance_read_policies(connection, role)
                connection.execute(text(f"SET LOCAL ROLE {role}"))
                assert connection.scalar(text("SELECT current_user")) == role
                assert tuple(connection.execute(text("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()) == (False,False)

                def db_dependency():
                    with TenantContextSession(bind=connection, join_transaction_mode="create_savepoint") as db:
                        yield db

                def principal_dependency(credentials=Depends(bearer), db=Depends(get_db)):
                    if credentials is None:
                        raise HTTPException(status_code=401)
                    profile = resolve_tenant_identity(db, credentials.credentials)
                    return SupabasePrincipal(profile['id'],profile['local_user_id'],profile['school_id'],profile['role'],bool(profile['is_admin']))

                # Real finance routers/dependencies and resolver, isolated test app.
                app = FastAPI()
                app.include_router(router)
                app.include_router(invoices_router)
                app.dependency_overrides[get_db] = db_dependency
                app.dependency_overrides[get_supabase_principal] = principal_dependency
                def claims(token):
                    return {"sub":str(UUID(int=int(token))),"role":"authenticated",
                            "user_metadata":{"role":"vortex_admin","school_id":2}}

                with patch('app.services.tenant_identity.verify_supabase_access_token', side_effect=claims), TestClient(app) as client:
                    assert client.get('/payments').status_code == 401
                    for uid, _, school in identities:
                        headers = {"Authorization":f"Bearer {uid}"}
                        with TenantContextSession(bind=connection, join_transaction_mode="create_savepoint") as db:
                            resolve_tenant_identity(db,str(uid))
                            permitted = uid in (1,2,3,4)
                            expected = {'students':[3] if uid==2 else [1,2],
                                'invoices':[3] if uid==2 else [1,2], 'payments':[2,20] if uid==2 else [1,21,22],
                                'payment_allocations':[20] if uid==2 else [10],
                                'invoice_lines':[2] if uid==2 else [1], 'receipts':[2] if uid==2 else [1]}
                            for table, ids in expected.items():
                                actual=db.execute(text(f"SELECT id FROM public.{table} ORDER BY id")).scalars().all()
                                assert actual == (ids if permitted else []), (uid,table,actual)
                            try:
                                db.execute(text("UPDATE public.payments SET amount=999"))
                            except DBAPIError as exc:
                                assert exc.orig.sqlstate=='42501'
                                db.rollback()
                            else:
                                raise AssertionError("Read-only role unexpectedly wrote financial data")
                        payments = client.get('/payments',headers=headers)
                        invoices = client.get('/invoices',headers=headers)
                        if not permitted:
                            assert payments.status_code==403 and invoices.status_code==403
                            continue
                        assert payments.status_code==200, payments.text
                        assert invoices.status_code==200, invoices.text
                        assert [p['id'] for p in payments.json()] == ([20,2] if uid==2 else [22,21,1])
                        wanted=[3] if uid==2 else [2,1]
                        assert [i['id'] for i in invoices.json()] == wanted
                        balances={i['id']:i['balance'] for i in invoices.json()}
                        assert balances == ({3:180} if uid==2 else {2:80,1:70}), balances
                        own_invoice=3 if uid==2 else 1
                        detail=client.get(f'/invoices/{own_invoice}',headers=headers)
                        assert detail.status_code==200 and len(detail.json()['lines'])==1
                        assert client.get(f'/invoices/{1 if uid==2 else 3}',headers=headers).status_code==404
                        assert client.get('/invoices/90',headers=headers).status_code==404
                        assert client.get(f'/payments?school_id={1 if uid==2 else 2}',headers=headers).status_code==403
                print("PASS: real finance read API with identity bootstrap and non-bypass RLS; two-school isolation; corrupt relationship denial; correct balances; unsupported roles and writes denied")
            finally:
                outer.rollback()
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT to_regclass('public.profiles')")) is None
            assert connection.scalar(text("SELECT count(*) FROM pg_roles WHERE rolname=:role"),{'role':role})==0
    finally:
        engine.dispose()
        unused_app_engine.dispose()


if __name__ == '__main__':
    run()
