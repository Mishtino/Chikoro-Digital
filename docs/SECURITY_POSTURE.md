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

The repository's three former migration drafts (`202611040001`–`003`) did not match the four migration versions recorded by the live Supabase project. They have been moved from `supabase/migrations/` to `supabase/proposed_migrations/` so the normal Supabase migration command cannot accidentally apply them. The standard migration directory now contains a README that explicitly blocks `supabase db push` until the original live migration SQL is recovered and a canonical history is reconstructed.

A proposed forward-only `profiles_role_check` migration is also stored in `supabase/proposed_migrations/`. It preserves live foreign keys, RLS flags, grants, and the own-profile SELECT policy. It is for staging review only. No production migration or identity link was applied.
