# Supabase migration directory

The four migration files in this directory were recovered from the live project's
`supabase_migrations.schema_migrations.statements` ledger on 5 November 2026.
Their version and name pairs match the four migrations reported as already
applied by the connected Supabase project:

- `20261104074727_create_profiles_identity_foundation.sql`
- `20261104082848_lock_down_public_data_api.sql`
- `20261104082933_add_verified_guardian_link_foundation.sql`
- `20261104083032_add_guardian_activation_fields.sql`

These are historical migrations, not new production changes. They are restored
so the repository contains the canonical migration history. No production
migration was run during recovery.

## New migrations remain gated

Do not move or apply anything from `supabase/proposed_migrations/` until it has
been tested against a staging clone and explicitly approved. The proposed
role allow-list, financial uniqueness, attendance register, timetable and
class-teacher assignment migrations are not part of the canonical migration
chain. In particular, the attendance/timetable/class APIs require their
corresponding proposed schema to be validated and applied in staging before
the code can be released. Do not copy these files into this directory as a
shortcut around the migration review.

See `docs/SUPABASE_MIGRATION_RECONCILIATION.md` for the recovery record,
schema differences, and release checklist.
