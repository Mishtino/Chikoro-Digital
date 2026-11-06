"""Keep proposed migrations quarantined until staging and release approval.

These checks are static safety gates, not a substitute for running SQL against
an isolated PostgreSQL staging clone.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "supabase" / "migrations"
PROPOSED = ROOT / "supabase" / "proposed_migrations"

EXPECTED_APPLIED = {
    "20261104074727_create_profiles_identity_foundation.sql",
    "20261104082848_lock_down_public_data_api.sql",
    "20261104082933_add_verified_guardian_link_foundation.sql",
    "20261104083032_add_guardian_activation_fields.sql",
}
STAGING_PROPOSALS = {
    "20261105_add_attendance_registers.sql",
    "20261105_add_class_teacher_assignments.sql",
    "20261105_add_financial_uniqueness_backstops.sql",
    "20261105_add_homework_assignments.sql",
    "20261105_add_parent_teacher_messaging.sql",
    "20261105_add_profiles_platform_role_allowlist.sql",
    "20261105_add_timetable_entries.sql",
}


def test_canonical_migration_chain_has_only_reconciled_live_history():
    assert {p.name for p in CANONICAL.glob("*.sql")} == EXPECTED_APPLIED


def test_staging_proposals_are_not_in_canonical_chain():
    assert STAGING_PROPOSALS <= {p.name for p in PROPOSED.glob("*.sql")}
    assert not STAGING_PROPOSALS.intersection({p.name for p in CANONICAL.glob("*.sql")})


def test_staging_proposals_have_explicit_transaction_boundaries():
    for name in sorted(STAGING_PROPOSALS):
        sql = (PROPOSED / name).read_text(encoding="utf-8")
        statements = [
            line.strip().upper()
            for line in sql.splitlines()
            if line.strip() and not line.lstrip().startswith("--")
        ]
        assert statements[0] == "BEGIN;", name
        assert statements[-1] == "COMMIT;", name


def test_financial_migration_rejects_cross_student_allocations():
    sql = (PROPOSED / "20261105_add_financial_uniqueness_backstops.sql").read_text(
        encoding="utf-8"
    ).lower()
    assert "join public.payments p on p.id = pa.payment_id" in sql
    assert "join public.invoices i on i.id = pa.invoice_id" in sql
    assert "pa.school_id <> p.school_id" in sql
    assert "pa.school_id <> i.school_id" in sql
    assert "p.student_id <> i.student_id" in sql
    assert "raise exception 'cross-school or cross-student payment allocations exist" in sql
