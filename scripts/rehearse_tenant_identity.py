"""Guarded, rollback-only identity bootstrap rehearsal on empty local PostgreSQL.

Uses the real profile resolver with representative public.users/profiles rows.
Token verification is mocked here; cryptographic verification has API tests.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from local_db_guard import validate_database_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from app.services.tenant_identity import resolve_tenant_identity
from app.tenant_context import TenantContextSession


def run():
    url = os.environ.get("DATABASE_URL", "")
    allowed, reason = validate_database_url(url)
    if not allowed:
        raise RuntimeError(f"Unsafe identity rehearsal target: {reason}")
    if os.environ.get("CHIKORO_REHEARSAL_IDENTITY") != "yes":
        raise RuntimeError("Explicit CHIKORO_REHEARSAL_IDENTITY=yes required")
    engine = create_engine("postgresql+psycopg" + url[url.index(":"):])
    role = "identity_rehearsal_" + uuid4().hex
    try:
        with engine.connect() as connection:
            outer = connection.begin()
            try:
                count = connection.scalar(text("""SELECT count(*) FROM pg_class c
                    JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f')"""))
                if count:
                    raise RuntimeError("Identity rehearsal requires an empty public schema")
                # Representative resolver columns only, not a Supabase schema clone.
                connection.execute(text("""CREATE TABLE public.users (
                    id int PRIMARY KEY, role text NOT NULL, school_id int,
                    is_admin boolean NOT NULL, is_active boolean NOT NULL,
                    password_hash text NOT NULL DEFAULT 'synthetic-secret');"""))
                connection.execute(text("""CREATE TABLE public.profiles (
                    id uuid PRIMARY KEY, local_user_id int UNIQUE REFERENCES public.users(id),
                    role text NOT NULL, school_id int, is_active boolean NOT NULL)"""))
                connection.execute(text("""INSERT INTO public.users (id,role,school_id,is_admin,is_active) VALUES
                    (1,'owner',1,false,true),(2,'owner',2,false,true),
                    (3,'owner',1,false,true),(4,'owner',2,false,true),
                    (5,'owner',1,false,true),(7,'owner',1,false,false),
                    (8,'admin',NULL,true,true)"""))
                rows = [(1,1,'owner',1,True),(2,2,'owner',2,True),
                        (3,3,'owner',1,False),(4,4,'owner',1,True),
                        (5,5,'teacher',1,True),(6,None,'pending',None,False),
                        (7,7,'owner',1,True),(8,8,'vortex_admin',None,True)]
                for identity, local_id, profile_role, school_id, active in rows:
                    connection.execute(text("INSERT INTO public.profiles VALUES (:id,:local_id,:role,:school,:active)"),
                        {"id": UUID(int=identity), "local_id": local_id, "role": profile_role, "school": school_id, "active": active})
                connection.execute(text(f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT"))
                connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
                connection.execute(text(f"GRANT SELECT (id,local_user_id,role,school_id,is_active) ON public.profiles TO {role}"))
                connection.execute(text(f"GRANT SELECT (id,role,school_id,is_admin,is_active) ON public.users TO {role}"))
                connection.execute(text("ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY"))
                connection.execute(text("ALTER TABLE public.users ENABLE ROW LEVEL SECURITY"))
                connection.execute(text(f"""CREATE POLICY identity_profile ON public.profiles FOR SELECT TO {role}
                    USING (id = NULLIF(current_setting('request.jwt.claim.sub',true),'')::uuid)"""))
                connection.execute(text(f"""CREATE POLICY identity_user ON public.users FOR SELECT TO {role}
                    USING (EXISTS (SELECT 1 FROM public.profiles p
                        WHERE p.local_user_id=users.id
                        AND p.id=NULLIF(current_setting('request.jwt.claim.sub',true),'')::uuid))"""))
                connection.execute(text(f"SET LOCAL ROLE {role}"))
                assert connection.scalar(text("SELECT current_user")) == role
                assert tuple(connection.execute(text("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()) == (False, False)

                def session():
                    return TenantContextSession(bind=connection, join_transaction_mode="create_savepoint")

                with session() as db:
                    assert db.execute(text("SELECT id FROM public.profiles")).all() == []
                    assert db.execute(text("SELECT id FROM public.users")).all() == []

                def resolve(db, identity, **extra):
                    claims = {"sub": str(UUID(int=identity)), "role": "authenticated", **extra}
                    with patch("app.services.tenant_identity.verify_supabase_access_token", return_value=claims):
                        return resolve_tenant_identity(db, "synthetic-token")

                with session() as db:
                    profile = resolve(db, 1, user_metadata={"role":"vortex_admin","school_id":2}, school_id=2)
                    assert profile["role"] == "owner" and profile["school_id"] == 1
                    assert db.scalar(text("SELECT current_setting('app.school_id')")) == '1'
                    assert db.execute(text("SELECT id FROM public.users")).scalars().all() == [1]
                    assert db.execute(text("SELECT id FROM public.profiles")).scalars().all() == [UUID(int=1)]
                    db.commit()
                    assert db.scalar(text("SELECT current_setting('app.school_id')")) == '1'
                    db.rollback()
                    assert db.execute(text("SELECT id FROM public.users")).scalars().all() == [1]
                    for statement in ("SELECT password_hash FROM public.users", "UPDATE public.profiles SET role='vortex_admin'", "DELETE FROM public.users"):
                        try:
                            db.execute(text(statement))
                        except DBAPIError as exc:
                            assert exc.orig.sqlstate == '42501', str(exc.orig)
                            db.rollback()
                        else:
                            raise AssertionError("Bootstrap role received excessive access")

                for identity in (3,4,5,6,7,9):
                    with session() as db:
                        try:
                            resolve(db, identity)
                        except HTTPException as exc:
                            assert exc.status_code == 403
                        else:
                            raise AssertionError(f"Invalid identity fixture {identity} accepted")
                        assert 'tenant_context' not in db.info and 'verified_subject' not in db.info
                        assert db.execute(text("SELECT id FROM public.users")).all() == []

                with session() as db:
                    with patch("app.services.tenant_identity.verify_supabase_access_token", side_effect=HTTPException(status_code=401)):
                        try:
                            resolve_tenant_identity(db, "invalid-token")
                        except HTTPException as exc:
                            assert exc.status_code == 401
                        else:
                            raise AssertionError("Invalid token accepted")
                    assert not db.in_transaction() and 'verified_subject' not in db.info

                for identity, school in ((2,'2'),(8,'')):
                    with session() as db:
                        resolve(db, identity)
                        assert db.scalar(text("SELECT current_setting('app.school_id')")) == school
                        assert db.scalar(text("SELECT current_setting('app.is_platform_admin')")) == 'false'
                        assert db.execute(text("SELECT id FROM public.users")).scalars().all() == [identity]
                print("PASS: real profile resolver under own-identity RLS; forged metadata ignored; inactive/unlinked/mismatched identities denied; narrow column grants; rollback recovery")
            finally:
                outer.rollback()  # also removes test role and tables
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT to_regclass('public.profiles')")) is None
            assert connection.scalar(text("SELECT to_regclass('public.users')")) is None
            assert connection.scalar(text("SELECT count(*) FROM pg_roles WHERE rolname=:role"), {"role": role}) == 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    run()
