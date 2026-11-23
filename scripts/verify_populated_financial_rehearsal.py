"""Verify the financial rehearsal refuses a populated disposable PostgreSQL DB.

Run only after the successful financial rehearsal in isolated CI PostgreSQL.
No schema modifications are made by this test.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg

from local_db_guard import validate_database_url


def main() -> None:
    url = os.environ.get("DATABASE_URL", "")
    allowed, reason = validate_database_url(url)
    if not allowed:
        raise RuntimeError(f"Unsafe verification target: {reason}")
    if os.environ.get("CHIKORO_REHEARSAL_EMPTY_DATABASE") != "yes":
        raise RuntimeError("Explicit empty-database rehearsal opt-in required")

    with psycopg.connect(url) as db:
        db.execute("SET TRANSACTION READ ONLY")
        before = tuple(
            db.execute(f"SELECT count(*) FROM public.{table}").fetchone()[0]
            for table in ("schools", "invoices", "payments", "payment_allocations")
        )
        if before[0] == 0:
            raise AssertionError("Expected populated financial rehearsal fixtures")

    script = Path(__file__).with_name("rehearse_financial_migration.py")
    result = subprocess.run(
        [sys.executable, str(script)], env=os.environ.copy(),
        capture_output=True, text=True, timeout=60, check=False,
    )
    if result.returncode == 0:
        raise AssertionError("Rehearsal unexpectedly accepted populated database")
    if "Refusing rehearsal: public schema is not empty" not in result.stderr:
        raise AssertionError(
            f"Unexpected refusal reason (exit {result.returncode}): {result.stderr[-1000:]}"
        )

    with psycopg.connect(url) as db:
        db.execute("SET TRANSACTION READ ONLY")
        after = tuple(
            db.execute(f"SELECT count(*) FROM public.{table}").fetchone()[0]
            for table in ("schools", "invoices", "payments", "payment_allocations")
        )
    assert after == before, f"Rejected rehearsal changed fixture counts: {before} -> {after}"
    print("PASS: populated PostgreSQL rehearsal refused; financial fixture counts unchanged")


if __name__ == "__main__":
    main()
