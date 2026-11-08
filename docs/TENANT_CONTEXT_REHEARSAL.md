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
