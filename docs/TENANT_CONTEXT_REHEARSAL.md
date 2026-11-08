# Tenant context foundation and isolated rehearsal

This is an opt-in staging foundation. The production Session factory and authentication dependencies do not import or use TenantContextSession. No live policy, role, grant or migration is changed.

The guarded `scripts/rehearse_tenant_context.py` runs in the existing isolated PostgreSQL 17 CI service after the financial rehearsal. It requires the existing loopback URL guard and `CHIKORO_REHEARSAL_TENANT_CONTEXT=yes`. It creates a unique synthetic schema and NOLOGIN role with no ownership, superuser or BYPASSRLS rights, tests a simple school policy, and cleans up those test objects. It does not touch the public schema or use production data.

The helper binds a verified Auth UUID, trusted local user ID, school and profile role before the first transaction. It reapplies parameterized transaction-local settings at every transaction begin, blanks all supported settings for missing context, refuses mid-transaction identity changes, and clears identity on Session close. Ordinary requests always have platform-admin false and request-kind ordinary; exceptional access is deliberately not implemented.

The rehearsal covers missing context; school A/B visibility; denied cross-school INSERT, UPDATE, DELETE and tenant reassignment; allowed own-school INSERT; commits, rollbacks and database errors; reuse of a closed Session; and successive principals on the same physical pooled connection. Tenant-free platform identities receive no implicit school access.

## Limits and next gates

- These are synthetic fixture policies, not policies for the actual application tables. This does not clear the full tenant-isolation release gate.
- Bind only from cryptographically verified identity and database-resolved profile data. Never pass request JSON or user-editable JWT metadata into context. Custom settings do not protect against arbitrary SQL execution under the same database role.
- Before production integration, implement verified-subject bootstrap for profile resolution, reconcile the route CRUD matrix and design exceptional activation, bootstrap, provider callback and reconciliation paths.
- Add reviewed table-specific policies and role grants, then verify real API workflows with representative schools, students, parents and teacher assignments in isolated Supabase staging.
- Validate connection-pool behavior in the deployed topology, Auth/Storage integration, advisors, migration recovery and rollback. Keep the existing production connection and feature gates unchanged until reviewed release approval.

References: [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security) and [SQLAlchemy Session events](https://docs.sqlalchemy.org/en/21/orm/session_events.html).

## Verified identity bootstrap rehearsal

`resolve_tenant_identity()` is an opt-in wrapper which verifies the access token using the existing verifier, sets only its verified subject, and invokes the existing live-profile resolver. Only after the resolver checks profile/local-user role, school and active-state parity does it attach full tenant context, including to the already-open transaction. It clears context and rolls back on rejection. No school or role is copied from JWT metadata. It is not wired into production dependencies.

`scripts/rehearse_tenant_identity.py` runs before the financial rehearsal and refuses any nonempty public schema. Within one outer transaction it creates representative users/profiles columns and synthetic rows, a non-owner/non-bypass NOLOGIN role, own-profile SELECT and linked-own-user SELECT policies, and column-specific SELECT grants that exclude password hashes. It exercises the real profile resolver and wrapper. All fixture DDL, role creation and rows are rolled back, and cleanup is checked before the financial rehearsal starts. It requires the loopback guard and `CHIKORO_REHEARSAL_IDENTITY=yes`.

Cases include missing identity, two schools, inactive profile, inactive user, pending/unlinked account, absent profile, role mismatch, school mismatch, forged user metadata, denied password-hash reads and identity writes, failed-token cleanup, context promotion, commit/rollback behavior and tenant-free platform identity without implicit platform-admin rights. The token verifier is mocked at its existing boundary in this rehearsal; existing API tests remain responsible for cryptographic JWT verification. Representative table columns and fixture policies are not a complete Supabase staging clone or an approved migration.

Remaining gates still include full policy review and implementation for actual application tables, restricted-role API integration, real Supabase Auth/Storage tests and the exceptional activation/callback/reconciliation workflows.
