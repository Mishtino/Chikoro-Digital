# Supabase migration reconciliation

**Project:** Chikoro Digital  
**Audit date:** 4 November 2026  
**Mode:** Read-only inspection; no migration or DDL was executed.

## Executive finding

The live Supabase migration ledger and the repository migration directory are not aligned. Do not run `supabase db push`, manually insert migration-history rows, or apply the repository SQL until the original four live migration definitions have been recovered and compared.

### Former repository migration drafts (now quarantined)

- `supabase/proposed_migrations/legacy_202611040001_profiles_identity_bridge.sql`
- `supabase/proposed_migrations/legacy_202611040002_vortex_platform_role.sql`
- `supabase/proposed_migrations/legacy_202611040003_vortex_staff_roles.sql`

These three drafts were removed from `supabase/migrations/` and preserved under `supabase/proposed_migrations/`. The standard migration directory contains a blocking README until the original live migration definitions are recovered. Do not run `supabase db push`.

### Live migration ledger

The connected project reports these applied versions:

- `20261104074727` — `create_profiles_identity_foundation`
- `20261104082848` — `lock_down_public_data_api`
- `20261104082933` — `add_verified_guardian_link_foundation`
- `20261104083032` — `add_guardian_activation_fields`

These are not the same migration versions or names as the three repository files. The original SQL for the four live ledger entries is not present in the current repository migration directory.

## Live schema observations

### `public.profiles`

The live table currently has:

- `id uuid` primary key referencing `auth.users(id)` with cascade delete.
- `local_user_id integer` unique, nullable, referencing `public.users(id)` with `ON DELETE SET NULL`.
- `role text NOT NULL DEFAULT 'pending'`.
- `school_id integer` nullable, referencing `public.schools(id)` with `ON DELETE SET NULL`.
- `is_active boolean NOT NULL DEFAULT false`.
- `created_at` and `updated_at` timestamps.

It currently has no role CHECK constraint. RLS is enabled but not forced. One SELECT policy exists for authenticated users, restricted to `auth.uid() = id`. The `authenticated` role has SELECT privilege on this table. The inspected public tables have RLS enabled; no public-table policies were found except this own-profile SELECT policy. The inspected `anon` and `authenticated` roles had no other table grants in the audited public schema.

### Differences from repository migration 001

The repository file `202611040001_profiles_identity_bridge.sql` uses `ON DELETE RESTRICT` for local-user and school foreign keys, while live uses `ON DELETE SET NULL`. It also specifies FORCE RLS and revokes all table privileges from `anon` and `authenticated`, whereas live currently allows authenticated own-profile SELECT.

Because `CREATE TABLE IF NOT EXISTS` does not reconcile an existing table's column definitions or foreign keys, applying this file to the live table would not make those definitions match. Its later ALTER/REVOKE statements would nevertheless change RLS and privileges and could remove a working profile-read path. Do not apply it as a schema repair.

### Platform owner identity bridge

The live audit found one unscoped local admin user and one unlinked profile. The profile is not linked to that local user. There are no orphaned non-null profile links and no profile whose Auth user is missing.

Do not infer that the unlinked profile belongs to the unscoped admin. The platform owner promotion migration only updates an already-linked profile and therefore cannot safely establish this identity link. A controlled linking process must verify the intended Auth UUID and local user record before any write.

## Safe reconciliation sequence

1. Obtain and preserve the exact SQL for all four applied live migrations from the original migration source or deployment history.
2. Compare those SQL files with the live catalog: table definitions, constraints, indexes, RLS flags, policies, grants, triggers, and functions.
3. Reconstruct a canonical local migration history that records the already-applied versions without re-running their DDL. Never fabricate ledger entries merely to silence a CLI mismatch.
4. Decide deliberately whether authenticated users should retain own-profile SELECT. Check every frontend and mobile client call path before changing the grant or policy.
5. Resolve the owner identity mapping through a verified, audited provisioning action. Do not auto-link based only on role, email resemblance, or an unscoped account.
6. Prepare a new forward-only migration for the platform role allow-list, preserving the live foreign-key delete actions and approved profile-read behaviour. Test it on a staging clone first.
7. Apply only after explicit production approval, then verify the migration ledger, role constraint, profile access policy, and owner permissions.

## Payment schema status

The read-only financial audit found zero rows in payments, payment allocations, receipts, invoices, and Paynow attempts. No duplicate Paynow references, duplicate payment/invoice allocation pairs, duplicate receipt numbers, cross-school allocations, or cross-student allocations were found. The live unique constraint on `(school_id, receipt_number)` exists. Database-level uniqueness for `payments.reference` and `(payment_id, invoice_id)` is still absent and should be introduced only through a separately reviewed forward migration.

## Operational guardrails

- No production migration was applied during this audit.
- No production data or user identity was changed.
- No Render environment variable or deployment was changed.
- The Vortex staff invitation endpoint must remain fail-closed until the live role allow-list is migrated and the required server-side Supabase Auth Admin secret is configured.


## Owner bootstrap readiness check

A read-only join found exactly one confirmed Supabase Auth identity matching the single active, unscoped local administrator by normalized email. The corresponding profile row remains unlinked; no identity mapping was written. The repository already contains a guarded `POST /auth/bootstrap-admin` endpoint that requires a 32+ character `ADMIN_BOOTSTRAP_TOKEN`, `VORTEX_PLATFORM_OWNER_EMAIL`, exactly one active unscoped local admin, and exactly one email-confirmed Auth identity. It refuses to run if a Vortex owner profile already exists and inserts the link only after those checks. The endpoint is not called during this audit. Before production use, verify the two Render environment variables are configured securely, and perform the bootstrap only with explicit approval. Regression tests for the endpoint have been added in `api/tests/test_bootstrap_admin.py`.


## RLS execution-role note

The live role catalog reports `postgres` and `service_role` as non-superuser roles with `BYPASSRLS`; `anon`, `authenticated`, and `authenticator` do not bypass RLS. This is a role capability finding, not confirmation of which database role Render currently uses. Verify the deployed API connection role through secret-safe configuration metadata before release. If it uses a BYPASSRLS role, every API route must enforce authentication, role authorization, and school/learner ownership in application queries; RLS alone is not a tenant boundary for that connection. Keep the browser roles restricted as currently observed.


## Proposed forward-only role allow-list

A further read-only check on 5 November 2026 found one live profile, with role `pending`, and zero profiles outside the current application role allow-list. The live `profiles` table still has no CHECK constraint.

A proposed migration is now stored separately at:

`supabase/proposed_migrations/20261105_add_profiles_platform_role_allowlist.sql`

It adds and validates only the `profiles_role_check` constraint. It does not recreate the table, alter foreign keys, change RLS/FORCE RLS, change grants or policies, or promote/link any user. It explicitly aborts if a constraint with that name already exists or if an existing profile role is outside the approved list.

**This is a staging proposal, not an applied migration and not yet in the standard `supabase/migrations` directory.** The four original live migration SQL definitions are still unavailable in the repository, so migration history reconciliation remains incomplete. Run this proposal only against a staging clone after comparing the original migration definitions and verifying the staging schema matches the audited live schema.


## Migration quarantine safeguard — 5 November 2026

The former repository migration drafts have been copied to `supabase/proposed_migrations/` and removed from `supabase/migrations/`. This prevents a routine Supabase CLI migration push from treating those unreconciled drafts as pending production migrations. `supabase/migrations/README.md` explicitly blocks pushes until the original four live SQL definitions are recovered. The proposed role allow-list SQL remains outside the standard migration path. This is a repository safety measure only; it does not alter the live Supabase migration ledger or database.
