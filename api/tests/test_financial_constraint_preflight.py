"""Guard against accidentally dropping financial migration preflight coverage.

This is a static regression gate, not a substitute for PostgreSQL staging
rehearsal or for verifying the actual definitions of existing constraints.
"""
from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase/proposed_migrations/20261105_add_financial_uniqueness_backstops.sql"
)

EXPECTED_CONSTRAINTS = {
    "uq_invoice_student_term_per_school",
    "uq_payment_reference_per_school",
    "uq_payment_allocation_per_invoice",
    "uq_invoice_school_id_id",
    "uq_payment_school_id_id",
    "fk_payment_allocation_payment_school",
    "fk_payment_allocation_invoice_school",
}


def test_all_financial_constraint_names_are_preflighted_before_ddl():
    sql = MIGRATION.read_text(encoding="utf-8")
    preflight, first_ddl = sql.split("ALTER TABLE public.invoices", 1)
    assert first_ddl
    for name in sorted(EXPECTED_CONSTRAINTS):
        assert f"conname = '{name}'" in preflight or (
            f"'{name}'" in preflight and "conname IN" in preflight
        ), f"Missing fail-closed preflight for {name}"


def test_financial_proposal_stays_transactional_and_quarantined():
    sql = MIGRATION.read_text(encoding="utf-8")
    statements = [
        line.strip().upper()
        for line in sql.splitlines()
        if line.strip() and not line.lstrip().startswith("--")
    ]
    assert statements[0] == "BEGIN;"
    assert statements[-1] == "COMMIT;"
    assert not (
        MIGRATION.parents[1] / "migrations" / MIGRATION.name
    ).exists(), "Proposed financial migration must not enter canonical chain"
