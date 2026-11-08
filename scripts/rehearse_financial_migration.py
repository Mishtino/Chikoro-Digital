"""Rehearse a proposed financial migration against an EMPTY local PostgreSQL DB.

Only the isolated Chikoro loopback target is accepted. Destructive test fixtures
must never be run against an existing database, staging, or production.
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg

from local_db_guard import validate_database_url

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db" / "schema.sql"
MIGRATION = ROOT / "supabase" / "proposed_migrations" / "20261105_add_financial_uniqueness_backstops.sql"


def run():
    url = os.environ.get("DATABASE_URL", "")
    allowed, reason = validate_database_url(url)
    if not allowed:
        raise RuntimeError(f"Unsafe PostgreSQL rehearsal target: {reason}")

    # A second explicit opt-in protects any existing local development data.
    if os.environ.get("CHIKORO_REHEARSAL_EMPTY_DATABASE") != "yes":
        raise RuntimeError("Set CHIKORO_REHEARSAL_EMPTY_DATABASE=yes for an EMPTY local test database")

    with psycopg.connect(url, autocommit=True) as db:
        non_system = db.execute(
            """SELECT count(*) FROM pg_class c
               JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')"""
        ).fetchone()[0]
        if non_system:
            raise RuntimeError("Refusing rehearsal: public schema is not empty")

        db.execute(SCHEMA.read_text(encoding="utf-8"))
        db.execute("""INSERT INTO schools (id, code, name) VALUES
                      (1, 'S1', 'School One'), (2, 'S2', 'School Two');
                      INSERT INTO students (id, school_id, student_number, first_name, last_name)
                      VALUES (1, 1, 'A', 'A', 'A'), (2, 1, 'B', 'B', 'B'),
                             (3, 2, 'C', 'C', 'C');
                      INSERT INTO terms (id, school_id, name, academic_year)
                      VALUES (1, 1, 'Term 1', '2026');
                      INSERT INTO invoices (id, school_id, student_id, term_id, invoice_number)
                      VALUES (1, 1, 1, 1, 'INV-1'), (2, 1, 2, 1, 'INV-2'),
                             (3, 2, 3, NULL, 'INV-3');
                      INSERT INTO payments (id, school_id, student_id, amount, reference)
                      VALUES (1, 1, 1, 30, 'PAY-1'), (2, 2, 3, 20, 'PAY-2');
                      INSERT INTO payment_allocations (id, school_id, payment_id, invoice_id, amount)
                      VALUES (1, 1, 1, 2, 10);""")

        migration = MIGRATION.read_text(encoding="utf-8")
        expected = (
            "uq_invoice_student_term_per_school", "uq_payment_reference_per_school",
            "uq_payment_allocation_per_invoice", "fk_payment_allocation_payment_school",
            "fk_payment_allocation_invoice_school", "uq_invoice_school_id_id",
            "uq_payment_school_id_id",
        )

        def financial_snapshot():
            # Compare every column, not just row counts: failed DDL must not
            # silently repair, delete or rewrite the conflicting evidence.
            return tuple(db.execute(f"SELECT * FROM public.{table} ORDER BY id").fetchall()
                for table in ('invoices', 'payments', 'payment_allocations'))

        def expect_preflight_failure(message):
            before = financial_snapshot()
            try:
                db.execute(migration)
            except psycopg.errors.RaiseException as exc:
                assert message in str(exc), str(exc)
                db.rollback()
            else:
                raise AssertionError(f"Migration incorrectly accepted: {message}")
            assert financial_snapshot() == before, "Failed migration altered financial evidence"
            names = db.execute(
                "SELECT conname FROM pg_constraint WHERE conname = ANY(%s)", (list(expected),)
            ).fetchall()
            assert not names, f"Failed preflight left partially applied constraints: {names}"

        expect_preflight_failure("Cross-school or cross-student")
        db.execute("DELETE FROM payment_allocations WHERE id = 1")
        # Each case has its own valid IDs, so the intended preflight rather
        # than an unrelated primary-key violation is what must reject it.
        cases = (
            ("Duplicate learner/term invoices", "invoices",
             "INSERT INTO invoices (id,school_id,student_id,term_id,invoice_number) VALUES (99,1,1,1,'DUP-TERM')"),
            ("Duplicate payment references", "payments",
             "INSERT INTO payments (id,school_id,student_id,amount,reference) VALUES (99,1,1,5,'PAY-1')"),
            ("Duplicate payment/invoice allocation pairs", "payment_allocations",
             "INSERT INTO payment_allocations (id,school_id,payment_id,invoice_id,amount) VALUES (98,1,1,1,5),(99,1,1,1,5)"),
            ("Cross-school or cross-student", "payment_allocations",
             "INSERT INTO payment_allocations (id,school_id,payment_id,invoice_id,amount) VALUES (99,2,1,3,5)"),
            ("Cross-school or cross-student", "payment_allocations",
             "INSERT INTO payment_allocations (id,school_id,payment_id,invoice_id,amount) VALUES (99,1,1,3,5)"),
        )
        for message, table, setup in cases:
            db.execute(setup)
            expect_preflight_failure(message)
            db.execute(f"DELETE FROM public.{table} WHERE id IN (98,99)")

        before = financial_snapshot()
        db.execute(migration)
        assert financial_snapshot() == before, "Successful migration rewrote financial data"
        # The proposal deliberately fails closed on repeat application; verify
        # that this preserves all existing constraints and financial records.
        try:
            db.execute(migration)
        except psycopg.errors.RaiseException as exc:
            assert "already exists; inspect it" in str(exc), str(exc)
            db.rollback()
        else:
            raise AssertionError("Repeated proposal should require inspection")
        assert financial_snapshot() == before
        names = {row[0] for row in db.execute(
            "SELECT conname FROM pg_constraint WHERE conname = ANY(%s)", (list(expected),)
        )}
        assert names == set(expected), f"Missing constraints: {set(expected) - names}"

        # Seed a valid allocation, then verify the uniqueness backstop rejects a repeat.
        db.execute("INSERT INTO payment_allocations (id, school_id, payment_id, invoice_id, amount) VALUES (10, 1, 1, 1, 5)")
        rejected = (
            ("duplicate payment allocation", "uq_payment_allocation_per_invoice", "INSERT INTO payment_allocations (id, school_id, payment_id, invoice_id, amount) VALUES (11, 1, 1, 1, 5)"),
            ("duplicate payment reference", "uq_payment_reference_per_school", "INSERT INTO payments (id, school_id, student_id, amount, reference) VALUES (11, 1, 1, 5, 'PAY-1')"),
            ("duplicate learner term invoice", "uq_invoice_student_term_per_school", "INSERT INTO invoices (id, school_id, student_id, term_id, invoice_number) VALUES (11, 1, 1, 1, 'INV-NEW')"),
            ("cross-school payment", "fk_payment_allocation_payment_school", "INSERT INTO payment_allocations (id, school_id, payment_id, invoice_id, amount) VALUES (12, 2, 1, 3, 5)"),
            ("cross-school invoice", "fk_payment_allocation_invoice_school", "INSERT INTO payment_allocations (id, school_id, payment_id, invoice_id, amount) VALUES (13, 1, 1, 3, 5)"),
        )
        for label, constraint, sql in rejected:
            try:
                db.execute(sql)
            except psycopg.errors.IntegrityError as exc:
                db.rollback()
                assert exc.diag.constraint_name == constraint, (
                    f"{label}: expected {constraint}, got {exc.diag.constraint_name}"
                )
            else:
                raise AssertionError(f"Database unexpectedly allowed {label}")

        # References are school-scoped, and NULL references remain repeatable.
        db.execute("""INSERT INTO payments (id, school_id, student_id, amount, reference)
                      VALUES (20, 2, 3, 5, 'PAY-1'), (21, 1, 1, 5, NULL),
                             (22, 1, 1, 5, NULL)""")

    print("PASS: isolated PostgreSQL financial-migration rehearsal and negative checks")


if __name__ == "__main__":
    run()
