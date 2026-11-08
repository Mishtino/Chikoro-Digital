"""Synthetic RLS/session rehearsal on guarded loopback PostgreSQL only.

Creates a unique test schema and NOLOGIN role, then removes only those objects.
This proves context mechanics, not deployed Supabase/application policies.
"""
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from local_db_guard import validate_database_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from app.tenant_context import TenantContext, TenantContextSession


def run():
    url = os.environ.get("DATABASE_URL", "")
    allowed, reason = validate_database_url(url)
    if not allowed:
        raise RuntimeError(f"Unsafe RLS rehearsal target: {reason}")
    if os.environ.get("CHIKORO_REHEARSAL_TENANT_CONTEXT") != "yes":
        raise RuntimeError("Explicit CHIKORO_REHEARSAL_TENANT_CONTEXT=yes required")
    suffix = uuid4().hex
    schema = "rls_rehearsal_" + suffix
    role = "rls_runtime_" + suffix
    engine = None
    with psycopg.connect(url, autocommit=True) as admin:
        # Commit setup atomically so a failed setup leaves no partial objects.
        with admin.transaction():
            admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT").format(sql.Identifier(role)))
            admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            admin.execute(sql.SQL("CREATE TABLE {}.records (id int PRIMARY KEY, school_id int NOT NULL, note text NOT NULL)").format(sql.Identifier(schema)))
            admin.execute(sql.SQL("INSERT INTO {}.records VALUES (1,1,'one'),(2,2,'two')").format(sql.Identifier(schema)))
            admin.execute(sql.SQL("ALTER TABLE {}.records ENABLE ROW LEVEL SECURITY").format(sql.Identifier(schema)))
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(role)))
            admin.execute(sql.SQL("GRANT SELECT,INSERT,UPDATE,DELETE ON {}.records TO {}").format(sql.Identifier(schema), sql.Identifier(role)))
            admin.execute(sql.SQL("""CREATE POLICY tenant_boundary ON {}.records TO {}
                USING (school_id = NULLIF(current_setting('app.school_id', true), '')::int)
                WITH CHECK (school_id = NULLIF(current_setting('app.school_id', true), '')::int)""").format(sql.Identifier(schema), sql.Identifier(role)))
        try:
            # The test connection starts in a non-owner, non-bypass role. Only
            # the synthetic local admin can assume it; no credentials are made.
            engine = create_engine(
                "postgresql+psycopg" + url[url.index(":"):],
                connect_args={"options": f"-c role={role}"},
                pool_size=1, max_overflow=0,
            )
            table = schema + ".records"  # internally generated identifier only
            def visible(session):
                return session.execute(text(f"SELECT id FROM {table} ORDER BY id")).scalars().all()

            first = TenantContext(UUID(int=1), 1, 1, "owner")
            second = TenantContext(UUID(int=2), 2, 2, "owner")
            with TenantContextSession(engine) as session:
                assert visible(session) == [], "Missing context must deny all rows"
                flags = session.execute(text("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()
                assert tuple(flags) == (False, False)
                assert session.scalar(text("SELECT current_user")) == role
                pid = session.scalar(text("SELECT pg_backend_pid()"))
                session.rollback()
                session.bind_tenant_context(first)
                assert visible(session) == [1]
                session.commit()
                assert visible(session) == [1], "Context lost after commit"
                session.rollback()
                assert visible(session) == [1], "Context lost after rollback"
                with session.begin_nested():
                    assert visible(session) == [1], "Context lost inside savepoint"
                try:
                    session.bind_tenant_context(second)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Context changed inside active transaction")
                assert session.execute(text(f"UPDATE {table} SET note='forbidden' WHERE id=2")).rowcount == 0
                assert session.execute(text(f"DELETE FROM {table} WHERE id=2")).rowcount == 0
                for statement in (
                    f"INSERT INTO {table} VALUES (3,2,'forbidden')",
                    f"UPDATE {table} SET school_id=2 WHERE id=1",
                ):
                    try:
                        session.execute(text(statement))
                    except DBAPIError as exc:
                        assert exc.orig.sqlstate == "42501", str(exc.orig)
                        session.rollback()
                    else:
                        raise AssertionError("RLS accepted a cross-school write")
                    assert visible(session) == [1], "Exception recovery lost tenant context"
                session.execute(text(f"INSERT INTO {table} VALUES (4,1,'allowed')"))
                session.commit()
                assert visible(session) == [1, 4]
                # A closed Session can be reused; it must not keep identity.
                session.close()
                assert visible(session) == [], "Closed Session retained tenant context"
                assert session.scalar(text("SELECT pg_backend_pid()")) == pid

            with TenantContextSession(engine) as session:
                session.bind_tenant_context(second)
                assert visible(session) == [2]
                assert session.scalar(text("SELECT pg_backend_pid()")) == pid
                session.rollback()
                session.bind_tenant_context(TenantContext(UUID(int=3), 3, None, "vortex_admin"))
                assert visible(session) == [], "Tenant-free principal gained implicit access"
                assert session.scalar(text("SELECT current_setting('app.is_platform_admin')")) == "false"
                assert session.scalar(text("SELECT current_setting('request.jwt.claim.sub')")) == str(UUID(int=3))
            with TenantContextSession(engine) as session:
                assert visible(session) == [], "Pooled connection leaked a previous identity"
                assert session.scalar(text("SELECT pg_backend_pid()")) == pid
            print("PASS: non-bypass RLS context, cross-school CRUD denial, commit/rollback/exception recovery, Session close and pooled connection reuse")
        finally:
            if engine is not None:
                engine.dispose()
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


if __name__ == "__main__":
    run()
