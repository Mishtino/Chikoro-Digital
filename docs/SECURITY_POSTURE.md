# Chikoro Digital security posture notes

This is a verified snapshot from the 4 November 2026 review. It records gaps that must be addressed before claiming production database hardening.

## Verified observations

- The connected Supabase database reports the application connection role as `postgres`, with `rolsuper = false` and `rolbypassrls = true`. The API therefore bypasses row-level security when it connects with this role. FastAPI tenant checks remain important, but RLS is not currently an independent backstop for API queries.
- Supabase Security Advisor reports RLS enabled with no policies on 20 public tables. This is fail-closed for browser roles; it is appropriate only while browser clients do not directly query those tables.
- The inspected web and Vortex portal source uses Supabase Auth in the browser and calls FastAPI for application data; no direct Supabase `.from(...)` table queries were found in those frontend files during this review.
- Supabase Auth leaked-password protection is disabled and should be enabled in the Auth security settings.

## Required hardening sequence

1. Inventory every FastAPI table operation, trigger, webhook, and background worker query, including required reads from `auth.users` and `public.profiles`.
2. Design a least-privilege application database role with only the required schema usage, table privileges, sequence privileges, and narrowly scoped access to identity tables. Do not store credentials in source control or browser environment variables.
3. Test the API, workers, payment callbacks, activation flows, reports, and migrations against that role in a staging environment before changing Render's database connection.
4. Add precise RLS policies only for any data that genuinely must be queried directly by browser clients. Keep privileged identity tables inaccessible to `anon` and `authenticated`.
5. Enable leaked-password protection and review MFA/session settings for Vortex platform operators.
6. Re-run Supabase Security Advisor and the full application test suite after each change.

## Current boundary

The Vortex role separation in the application is implemented in FastAPI and the Vortex portal, but the role migration and owner bootstrap are not applied to the live project in this code change. The database connection role has not been changed. Do not treat this snapshot as a production-hardening sign-off.


## Payment integrity controls reviewed on 4 November 2026

- Manual payments and verified Paynow settlement serialize receipt allocation by locking the school row before locking invoice rows. The lock order is intentionally consistent across both flows.
- Invoice balances count only non-void payments whose payment school, allocation school, invoice school, and learner identity agree. Malformed cross-school or cross-learner allocations do not reduce another learner's balance.
- Paynow settlement rechecks the outstanding invoice/student balance while holding the relevant invoice locks. A stale checkout cannot create a payment that exceeds the remaining balance.
- Receipt numbering uses the highest existing numeric receipt suffix rather than row count, so a deleted or missing receipt number is not reused. The school lock protects concurrent manual and Paynow receipt generation.
- Webhook and reconciliation settlement share the same verified-payment recording helper. Provider confirmation must be hash-verified and match the exact local reference and amount.
- Regression tests cover duplicate callbacks, cross-school invoice linkage, cross-learner allocation rows, stale balances, late cancellation callbacks, and receipt sequence gaps.

## Financial schema work still pending

- payments.reference does not yet have a database uniqueness constraint. Paynow attempts are serialized by row locks and use deterministic paynow:{attempt_id} references, but a database-level unique constraint is still the desired final integrity backstop.
- payment_allocations does not yet have a database uniqueness or composite tenant-integrity constraint.
- Before adding these constraints, run read-only duplicate/orphan/mismatch reports against a production snapshot, resolve any historical exceptions, prepare a forward-only Supabase migration, and verify it against staging. No production migration is authorized by this review.
- Receipt uniqueness is already represented in the SQLAlchemy model as (school_id, receipt_number); verify that the live database has the matching constraint before relying on it as a production guarantee.


## Read-only live database audit — 4 November 2026

The connected Supabase project was queried without modifying data:

- `payments`: 0 rows; `payment_allocations`: 0 rows; `receipts`: 0 rows; `invoices`: 0 rows; `paynow_attempts`: 0 rows.
- Duplicate Paynow payment references, duplicate `(payment_id, invoice_id)` allocation pairs, duplicate receipt numbers, cross-school allocations, and cross-student allocations each returned zero issue groups.
- The live database has `receipts_school_id_receipt_number_key` as a unique constraint on `(school_id, receipt_number)`.
- The live database has no unique constraint on `payments.reference` and no unique constraint on `(payment_id, invoice_id)` in `payment_allocations`.
- The live `supabase_migrations.schema_migrations` history currently lists four applied migrations: `create_profiles_identity_foundation`, `lock_down_public_data_api`, `add_verified_guardian_link_foundation`, and `add_guardian_activation_fields`. Reconcile this history with repository migration files before applying any further migration.
- The live `public.profiles` table currently has no CHECK constraints. The platform staff invitation path therefore remains correctly fail-closed until the role constraint migration is reconciled and applied through the approved release process.

These are point-in-time findings, not a guarantee that the database remains unchanged. No SQL DDL, data writes, migration application, or production configuration changes were made during this audit.


## Migration history quarantine — 5 November 2026

The repository's three former migration drafts (`202611040001`–`003`) did not match the four migration versions recorded by the live Supabase project and remain quarantined under `supabase/proposed_migrations/`. The exact four applied SQL definitions were recovered from `supabase_migrations.schema_migrations.statements` and restored under their original version/name pairs in `supabase/migrations/`.

The proposed forward-only `profiles_role_check` and financial uniqueness migrations remain under `supabase/proposed_migrations/`, outside the standard migration path. They are for staging review only. No production migration or identity link was applied.


## Financial uniqueness backstops prepared — 5 November 2026

The live read-only audit found zero duplicate non-NULL payment references (including within schools) and zero duplicate `(payment_id, invoice_id)` allocation pairs. The SQLAlchemy models now declare a unique `(school_id, reference)` constraint for non-NULL payment references and a unique `(payment_id, invoice_id)` constraint for allocations. Tests verify that a school may reuse an external reference used by another school, but cannot duplicate its own, and that one payment cannot allocate twice to the same invoice.

A corresponding staging-only SQL proposal is stored at `supabase/proposed_migrations/20261105_add_financial_uniqueness_backstops.sql`. It checks for duplicates and pre-existing constraints before adding either unique constraint. These constraints have **not** been applied to the live database. The proposal notes that PostgreSQL unique-constraint creation takes table locks and must be scheduled appropriately after staging review.


## Render deployment and effective database role — 5 November 2026

The Render service `Chikoro-Digital` is connected to `Mishtino/Chikoro-Digital`, deploys from `main`, and has `autoDeploy=yes`. The latest observed deployment is live at commit `18ee44a066d2f49371d5a16f6b9e75e6c4a0db02`. This was triggered automatically by the Git push; no manual deploy was invoked. Render startup logs confirm the API connects as database role `postgres`, with `rolsuper=false` and `rolbypassrls=true`. Therefore RLS does not independently constrain API queries. The deployment's startup logs showed no warning/error records or HTTP 5xx request records in the inspected 03:50–04:10 UTC window. No Render environment variables or Supabase schema were changed by this work.

The repository also has four Vercel projects linked to this GitHub repository. Vercel automatically created production deployments for earlier `main` commits; the latest code SHA `18ee44a...` and latest `main` SHA were not present in the Vercel deployment records inspected. These deployments were not manually triggered. Future Git pushes can trigger Render and Vercel production deploys because automatic deployment is enabled; use a release branch or explicitly disable auto-deploy only with approval before further code pushes if production deployment must be held.


## Class-level authorization, attendance and timetable — 5 November 2026

The feature branch now includes proposed attendance registers, class timetables and teacher-to-class assignments. Teacher access to learner records, mark entry and attendance registers is restricted to active assigned classes; teacher timetable reads are limited to assigned classes or timetable periods directly assigned to the teacher. School owners/headmasters manage class assignments. Teachers cannot create learner records or manage assignments.

Composite tenant foreign keys are proposed for attendance sessions/records, timetable entries and class assignments. Supporting unique keys on `users`, `students`, `terms` and `subjects` are included in proposed SQL only. The relevant files remain outside `supabase/migrations/`; none of these migrations has been applied to staging or production. RLS is enabled in the proposals with no browser-facing policies, and the live Render role remains `postgres` with `BYPASSRLS=true`. Therefore these additions are not production-ready until a least-privilege API database role, migration validation, tenant-negative tests and direct browser-role RLS tests are completed.

CI run `41998128269` passed API tests and both frontend builds for the attendance/timetable work. Class assignment and class-level authorization changes are under validation in subsequent CI runs. No production data, schema, environment variables, deployments or credentials were changed.
