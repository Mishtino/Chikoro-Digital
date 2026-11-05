# Runtime database least-privilege plan

**Status:** investigation and design only — no database DDL, grants, role creation, password changes, or Render configuration changes have been performed.

**Project:** Chikoro Digital  
**Supabase project:** `xivzduvqpuqbecskxaoj`  
**Reviewed:** 5 November 2026  
**Working branch:** `work/migration-and-financial-hardening-20261105`

## Executive finding

The Render API currently connects as the Supabase `postgres` role. The live role is not a PostgreSQL superuser, but it has `BYPASSRLS`; the API therefore bypasses row-level security. This is a significant privilege concentration and means tenant isolation currently depends on FastAPI authorization and school-scoped SQL.

A replacement runtime identity is required, but changing the connection string before the access model is ready would break the application. The live schema currently has RLS enabled on all 21 public base tables, but only one public RLS policy exists: authenticated users may select their own `profiles` row. The other 20 public tables have no policies. A non-BYPASSRLS API role would therefore be denied access to most application data until an explicit server-side RLS context and policies are designed and tested.

## Read-only live observations

- The current database role is `postgres`: `rolsuper = false`, `rolbypassrls = true`, `rolcreatedb = true`, and `rolcreaterole = true`.
- The built-in `service_role` is also `rolbypassrls = true` (and is non-login here); it is not an acceptable replacement. The `authenticator` login role can assume `anon`, `authenticated`, and `service_role`; the new API runtime must not inherit any of these elevated paths.
- All 21 public base tables have RLS enabled; none currently has FORCE ROW LEVEL SECURITY.
- Only `public.profiles` has a policy, for `SELECT` by `authenticated` where `auth.uid() = id`.
- The other 20 public tables have no policies. A fresh grant audit also found that `anon` has no table-level DML privileges on any public base table, and `authenticated` has table-level access only to `profiles` (SELECT); neither role has CREATE on the public schema. This is fail-closed for browser Data API access, but it also means a normal non-bypass runtime role cannot yet serve the existing API.
- The `public` schema currently grants CREATE to `postgres`; the API runtime must not receive CREATE, ownership, ALTER, DROP, TRUNCATE, TRIGGER, or REFERENCES privileges.
- The API currently performs read-only lookups in `auth.users` for bootstrap and student/parent activation. Prefer the Supabase Auth user/Admin API for these identity checks so the runtime does not need direct `auth.users` access.
- The only trigger discovered in `public`/ `auth` is `auth.users` AFTER INSERT calling `private.handle_new_auth_user()`. That function is SECURITY DEFINER, owned by `postgres`, and uses `search_path = pg_catalog, public`; it inserts a pending profile. The API runtime should not receive access to the `private` schema or EXECUTE rights on this trigger function.
- The background worker is currently a placeholder and does not yet query the database. It must not be granted production data access until its real jobs are implemented and inventoried.
- The current SQLAlchemy `get_db()` dependency does not set JWT claims or tenant context. `get_supabase_principal()` verifies the token and resolves a profile, but a staged no-bypass design must set verified `auth.uid()` context before that profile lookup and reapply context after each transaction restart.
- Paynow webhook has no Supabase principal, while reconciliation is a cross-school platform-owner operation. These need separate, narrowly scoped policies/identities; they must not be treated as normal school requests.

## Public application tables

The live public schema contains these 21 base tables:

`assessments`, `audit_logs`, `contacts`, `fee_items`, `fee_structure_items`, `fee_structures`, `guardian_links`, `invoice_lines`, `invoices`, `marks`, `notifications`, `payment_allocations`, `payments`, `paynow_attempts`, `profiles`, `receipts`, `schools`, `students`, `subjects`, `terms`, `users`.

SQLAlchemy models cover the school, user, student/contact, fee, results, audit, payment, Paynow and notification tables. `profiles` and `guardian_links` are accessed using explicit SQL. Route-level read/write operations still need a complete matrix before table grants are finalized.

## Target architecture

1. Create a dedicated runtime role, separate from `postgres`, `service_role`, `authenticated`, and `anon`. It must not be a member of any elevated role and must have `rolsuper = false` and `rolbypassrls = false`.
2. Keep ownership and migration privileges with the migration/admin identity. The runtime role must not own application tables or schemas.
3. Grant only `USAGE` on the required schema(s), table-level DML required by the verified API matrix, and `USAGE`/ `SELECT` on only the sequences used by inserts. Do not use blanket ALL privileges as the final grant design. Do not substitute Supabase's built-in `service_role`, because it bypasses RLS.
4. For `auth.users`, grant only the minimum read access required for verified account activation. Do not grant INSERT, UPDATE, DELETE, or access to unrelated Auth tables.
5. Design server-side tenant context and RLS policies before using a non-BYPASSRLS role. Context must be set only after Supabase JWT verification and trusted profile resolution. Policies must distinguish school-scoped users from Vortex platform roles and protect every tenant-owned table, including joins and payment allocations.
6. Keep `profiles` and guardian-link access especially narrow. Platform identity lookups and bootstrap flows must be explicitly represented in the access design.
7. Keep the notification worker on a separate identity with only the permissions needed by its eventual queue/notification jobs. Do not reuse the API role by default.
8. Use a separate staging database/branch with representative data. Run the full API, portal, activation, Paynow webhook/reconcile, admin, audit, and worker tests using the candidate runtime role before any production credential switch.
9. Prepare a rollback connection string and a controlled cutover plan. Rotate the runtime credential through Render's secret environment only after staging passes; never commit credentials or put them in browser-visible `NEXT_PUBLIC_*` variables.

## Required inventory before grants

The next code-review pass must produce a table-by-table matrix with:
- API route/service and SQLAlchemy model or raw SQL reference;
- SELECT / INSERT / UPDATE / DELETE operations actually used;
- tenant key and trusted principal requirement;
- whether the route is school-scoped or Vortex platform-wide;
- whether the table is accessed in authentication/bootstrap paths;
- sequence usage and trigger/function dependencies;
- corresponding RLS policy and negative cross-school test.

The matrix must cover all API routers, shared services, startup code, scheduled jobs, webhooks, and the worker. The current worker is a placeholder; its future database access is not assumed.

## Staging acceptance criteria

- Candidate role has no superuser, BYPASSRLS, ownership, schema CREATE, or elevated role membership.
- No access to `private` or unrelated `auth` objects.
- API happy-path tests pass for school admin, teacher, bursar, student, parent, and Vortex roles.
- Cross-school and cross-student negative tests prove rows cannot be read or modified by the wrong principal.
- Parent/student activation, platform staff lifecycle, audit writes, payment receipt generation, Paynow callback and reconciliation flows pass.
- Inserts work with only the required sequences.
- Data API access remains denied unless a deliberate browser access path and matching RLS policy are approved.
- Security Advisor and full CI pass; runtime logs show the new non-bypass role.
- Rollback to the previous connection is rehearsed in staging.

## Release gate

This plan is not permission to make production changes. Do not create the role, apply RLS policies or grants, change Render's `DATABASE_URL`, or apply pending migrations until the table/route inventory is complete, staging validation passes, and the production cutover is explicitly approved.

At release time, deploy the database changes first in a backward-compatible manner, then API code and environment configuration, then web/admin frontends, and finally run smoke tests and verify the actual deployed commit on Render and every Vercel project. Do not merge or push release commits to `main` until the coordinated release window is confirmed because Render auto-deploys from `main`.
