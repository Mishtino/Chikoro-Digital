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


The proposed parent/teacher messaging migration (`20261105_add_parent_teacher_messaging.sql`) is also staging-only. It creates school-scoped conversations and messages, composite tenant foreign keys, RLS with no browser-facing policies, and no direct grants to `anon` or `authenticated`. Apply it only after the verified guardian, class assignment, and supporting composite-key migrations have been reviewed and validated together. Messaging APIs must not be released before this schema is present in the target environment.

The proposed homework migration (`20261105_add_homework_assignments.sql`) is staging-only. It adds school-scoped assignments and one text submission per learner, with composite tenant foreign keys and RLS enabled without browser-facing policies. The homework schema also includes a private `homework-private` Storage bucket (10 MiB object limit and an explicit document/image MIME allow-list), tenant-scoped attachment metadata, and composite school/submission/uploader foreign keys. The API uses server-side signed upload/download URLs; no public bucket or browser service key is used. Uploads are checked against the declared MIME type and byte size before becoming visible. The migration adds its own required (school_id, id) unique keys for users, students, terms, subjects and submissions inside one transaction, so it does not depend on the attendance or timetable migrations being applied first. Test the Storage API response shape, browser upload CORS, file limits and tenant authorization before deploying the API/UI. Do not deploy the homework API until the schema and private bucket are present in the target environment.

### Proposed migration transaction and dependency review

All five current 20261105_add_*.sql proposed migrations are wrapped in explicit
PostgreSQL transactions (BEGIN/COMMIT). A failure must roll back the whole
migration rather than leave a partial schema. Each migration creates the
composite unique keys required by its own foreign keys, so the attendance,
class-assignment, homework, messaging and timetable schema files can be
validated independently on a clean staging clone. For the integrated parent/
teacher messaging workflow, validate and apply the class-teacher-assignment
schema before enabling the messaging API, because message authorization relies
on active class assignments. Keep every proposed migration out of the
production migration chain until staging validation and release approval.
