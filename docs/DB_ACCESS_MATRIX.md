# Chikoro Digital API database access matrix

**Status:** first-pass static inventory, 5 November 2026. This is not a grant script and is not a production authorization change.

Source reviewed on branch `work/migration-and-financial-hardening-20261105`: all 13 API routers, SQLAlchemy model declarations, shared services, `deps_supabase.py`, and the current worker placeholder. A final pass must inspect every SQL statement and endpoint branch before grants or RLS policies are approved.

## Router-to-table map

| Router / component | Tables referenced through models or explicit SQL | Observed access pattern |
|---|---|---|
| `auth.py` | `users`, `students`, `contacts`, `profiles`, `guardian_links`, `audit_logs`, `auth.users` | Reads identity and activation state; creates/updates local users, profiles, guardian links, activation records and audit events. `auth.users` is read-only from the API. |
| `fees.py` | `terms`, `fee_items`, `fee_structures`, `fee_structure_items`, `invoices`, `invoice_lines`, `students`, `schools` | Reads and creates fee configuration and invoices; updates current-term flags. |
| `notifications.py` | `notifications` | Reads notification records. |
| `payments.py` | `invoices`, `invoice_lines`, `payments`, `payment_allocations`, `receipts`, `students`, `schools` | Reads balances and creates payment, allocation and receipt records. |
| `paynow.py` | `schools`, `students`, `invoices`, `payments`, `payment_allocations`, `receipts`, `paynow_attempts`, `guardian_links`, `contacts` | Reads configuration, learner/guardian links and balances; creates and updates Paynow attempts; verified settlement creates payments, allocations and receipts. |
| `platform_access.py` | No direct table access | Uses the resolved principal and permission map. |
| `platform_audit.py` | `audit_logs`, `schools`, `users` | Reads audit records and actor/school metadata. |
| `platform_staff.py` | `profiles`, `users`, `audit_logs` | Reads staff identities; creates local staff and profile links; updates active state; writes audit events. |
| `portal.py` | `students`, `contacts`, `invoices`, `marks`, `assessments`, `subjects`, `terms`, `users`, `guardian_links` | Reads portal identity, verified guardian links, fees and published academic data. |
| `results.py` | `subjects`, `assessments`, `marks`, `students`, `terms`, `notifications`, `contacts` | Reads and writes academic setup/results and creates notification records. |
| `schools.py` | `schools` | Reads, creates and updates school records. |
| `students.py` | `students`, `contacts`, `schools`, `users`, `audit_logs` | Reads and creates students, users and guardian contacts; updates activation PIN state; writes audit events. |
| `users.py` | `users` | Reads school user directory. Legacy local-password creation is disabled. |
| Shared `money.py` | `invoices`, `payments`, `payment_allocations`, `receipts` | Reads scoped payment allocations/balances and creates receipts. |
| Shared `supabase_auth.py` / `platform_access.py` | `profiles`, `users` | Resolves trusted Supabase identity to the local account and trusted role. |
| Worker | None currently | Placeholder only; future notification, Paynow and PDF tasks are not implemented and must be inventoried separately. |

## Tables not yet covered by a completed privilege decision

The 21 public tables are all represented in the map above, but this first pass does not yet establish the exact minimum command privilege for each one. In particular:
- `notifications` is read by its router and written by the results flow; there is no live worker consumer yet.
- `profiles` and `guardian_links` are accessed through raw SQL, so their operation set must be checked statement by statement.
- Some endpoints commit multiple times and then write audit events. Any transaction-local RLS context must be tested across those commits.
- Platform-wide operations (school directory, Vortex staff, audit) need explicit policy treatment that does not accidentally grant school users cross-tenant visibility.
- Authentication bootstrap and student/parent activation are not ordinary school-scoped endpoints; they require dedicated policy tests. Current source confirms these paths directly query `auth.users`; prefer Supabase Auth user/Admin API lookups rather than broad database grants.
- The Paynow webhook has no Supabase principal and performs lookup/settlement; reconciliation scans across schools under a platform-owner route. Both need separate narrowly scoped database access boundaries.
- The API uses both SQLAlchemy ORM and raw SQL. A grep-only inventory is insufficient to finalize grants.

## Initial privilege boundaries

| Object | Candidate runtime access | Explicitly not allowed |
|---|---|---|
| `public` schema | USAGE only | CREATE, ownership, ALTER/DROP |
| Application tables | Only table-specific SELECT/INSERT/UPDATE/DELETE after the endpoint matrix is signed off | TRUNCATE, REFERENCES, TRIGGER, blanket ALL |
| Public sequences | USAGE/SELECT only for sequences actually used by inserts | OWNERSHIP or sequence ALTER |
| `auth.users` | SELECT only for the exact activation/verification lookups | INSERT, UPDATE, DELETE |
| `private` schema | No access | USAGE, CREATE, function execution |
| Auth internals other than required `auth.users` lookup | No access | Broad schema/table grants |
| Migration and ownership privileges | Separate migration/admin identity only | Runtime inheritance or role membership |

## RLS and tenant context

A dedicated role with `BYPASSRLS = false` cannot be switched into production safely while 20 public tables still have no policies. The built-in Supabase `service_role` also has `BYPASSRLS = true` and must not be used as a shortcut. The current SQLAlchemy Session has no request-context setup; verified JWT subject context must be set before own-profile resolution and reapplied after every new transaction. Before cutover, define trusted request context from the verified Supabase principal, and policies for every tenant-owned table and relationship. Cover school-scoped users, students, parents/guardian links, and Vortex platform roles separately. Test both positive and negative cross-school access.

Do not solve this by granting the runtime role `BYPASSRLS` and calling the result RLS hardening. A no-bypass role plus deliberate RLS policies is the target. Also do not assume that adding a role or policies alone protects against arbitrary SQL injection; parameterized SQL, safe query construction, least privilege, and application authorization remain required.

## Completion checklist

- [ ] Endpoint-by-endpoint CRUD and sequence map verified from source.
- [ ] Every raw SQL statement, startup hook, dependency, webhook and background job reviewed.
- [ ] RLS context design reviewed for authentication, multi-commit requests and error cleanup.
- [ ] Policy matrix covers all 21 public tables and all relationship/financial tables.
- [ ] Staging database has representative schools, learners, guardians, payments and staff roles.
- [ ] Candidate no-BYPASSRLS runtime role passes full API and negative tenant-isolation tests.
- [ ] Runtime grants are generated from the final matrix, not blanket defaults.
- [ ] Render connection switch and rollback rehearsed in staging.

See [DB_LEAST_PRIVILEGE_PLAN.md](DB_LEAST_PRIVILEGE_PLAN.md) for live observations, target architecture and release gates, and [RLS_POLICY_DESIGN.md](RLS_POLICY_DESIGN.md) for exceptional-path and request-context design.
