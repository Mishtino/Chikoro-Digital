# Chikoro Digital API database access matrix

**Status:** first-pass static inventory, 5 November 2026. This is not a grant script and is not a production authorization change.

Source reviewed on branch `work/migration-and-financial-hardening-20261105`: all 13 API routers, SQLAlchemy model declarations, shared services, `deps_supabase.py`, and the current worker placeholder. A final pass must inspect every SQL statement and endpoint branch before grants or RLS policies are approved.

## Router-to-table map

| Router / component | Tables referenced through models or explicit SQL | Observed access pattern |
|---|---|---|
| `auth.py` | `users`, `students`, `contacts`, `profiles`, `guardian_links`, `audit_logs`, `auth.users` | Reads identity and activation state; creates/updates local users, profiles, guardian links, activation records and audit events. `auth.users` is read-only from the API. |
| `fees.py` | `terms`, `fee_items`, `fee_structures`, `fee_structure_items`, `invoices`, `invoice_lines`, `students`, `schools` | Reads and creates fee configuration and invoices; updates current-term flags. |
| `notifications.py` | `notifications` | Reads notification records; the process endpoint currently fails closed with HTTP 501 and does not mark messages as delivered because no provider is configured. |
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


## CRUD and grant decision draft — route/write-site pass

This addendum records a second static pass over the route decorators and explicit ORM/raw-SQL write sites in all 12 router modules. It is still a **candidate grant matrix**, not an approved grant script. ORM relationships, model cascades, background work, and all implicit SQLAlchemy flushes must be checked before finalizing grants.

| Table | Candidate runtime commands | Evidence / constraints |
|---|---|---|
| `schools` | SELECT, INSERT, UPDATE | School create/list/detail/update/status routes. UPDATE must be limited to Vortex lifecycle actions or the owning school administrator as appropriate. |
| `users` | SELECT, INSERT, UPDATE | Auth activation, student onboarding, staff lifecycle, school user directory and principal resolution. No runtime DELETE identified. |
| `profiles` | SELECT, INSERT, UPDATE | Raw SQL identity resolution, activation/bootstrap/staff profile linking and status changes. Preserve own-profile browser SELECT separately. |
| `students` | SELECT, INSERT, UPDATE | Student create, activation and portal/fee/results lookups. Parent visibility must be relationship-derived, never caller-supplied student ID alone. |
| `contacts` | SELECT, INSERT, UPDATE | Student onboarding, guardian activation, verified parent relationship and portal lookups. |
| `guardian_links` | SELECT, INSERT, UPDATE | Parent activation and verified guardian resolution; no client-side direct link writes. |
| `terms` | SELECT, INSERT, UPDATE | Term create/list and current-term switching; update must remain school-scoped. |
| `fee_items` | SELECT, INSERT, UPDATE | Fee item create/list and fee configuration maintenance. |
| `fee_structures` | SELECT, INSERT, UPDATE | Fee structure create/list and term/school validation; confirm whether any update route exists before granting UPDATE. |
| `fee_structure_items` | SELECT, INSERT | Created during fee structure creation; no direct update/delete route found. |
| `invoices` | SELECT, INSERT, UPDATE | Invoice generation, fee status and balance/payment workflows. UPDATE is required only if source paths actually mutate invoice state; verify each ORM flush before final grant. |
| `invoice_lines` | SELECT, INSERT | Generated with invoices; no independent update/delete route found. |
| `payments` | SELECT, INSERT, UPDATE | Manual payment creation, Paynow settlement and voiding. UPDATE must be constrained to settlement/void state transitions. |
| `payment_allocations` | SELECT, INSERT | Created as part of verified payment settlement/manual allocation. No independent update/delete route found. |
| `receipts` | SELECT, INSERT | Receipt creation and lookup. No update/delete route found. |
| `paynow_attempts` | SELECT, INSERT, UPDATE | Checkout initiation, webhook state transitions, polling and reconciliation. Provider callback path requires its own narrow identity/context. |
| `subjects` | SELECT, INSERT, UPDATE | Subject create/list and results/report-card reads; verify whether update is currently used before granting it. |
| `assessments` | SELECT, INSERT, UPDATE | Assessment create/list, approval/publication state and report-card reads. |
| `marks` | SELECT, INSERT, UPDATE | Mark entry, approval/publication and report-card/portal reads. |
| `notifications` | SELECT, INSERT, UPDATE | Results publication queues notifications; process route updates delivery state. No worker exists yet. |
| `audit_logs` | SELECT, INSERT | Platform/school audit reads and append-only event writes. Do not grant UPDATE or DELETE to the API runtime. |

### Explicitly withheld privileges

- No `DELETE`, `TRUNCATE`, `REFERENCES`, or `TRIGGER` privilege has been identified as necessary for the current API.
- No application runtime ownership, schema `CREATE`, `ALTER`, or `DROP`.
- No access to `private` schema or execution of `private.handle_new_auth_user()`.
- No blanket grants to `PUBLIC`, `anon`, `authenticated`, or the built-in `service_role`.
- No `auth.users` grant is approved. Replace direct Auth-table lookups with a verified Supabase Auth Admin API/user lookup where feasible; if any direct lookup remains, document its exact query and request path first.
- Sequence `USAGE`/`SELECT` grants must be generated only for sequences actually referenced by identity/serial inserts after inspecting the live schema and ORM insert behavior.

### Route-specific exceptions and transaction hazards

- `auth.py`: bootstrap and student/parent activation are pre-school-context flows. They cannot receive a generic tenant policy. The first-owner bootstrap must remain one-time and operationally gated.
- `paynow.py`: webhook has no Supabase bearer principal; reconciliation is cross-school. Do not grant these paths generic platform-wide access. Prefer separate service identities or narrowly bounded database functions with reviewed inputs and fixed search paths; never add a broad SECURITY DEFINER function as a shortcut.
- `platform_staff.py` and `platform_audit.py`: require explicit platform permission context. Support, auditor, billing and owner roles must not share one blanket cross-tenant policy.
- Multiple routes call `db.commit()` during a request. Transaction-local RLS context must be re-established on every new transaction and must be tested through commit, rollback and pooled connection reuse.
- Several routes use ORM relationship flushes. Confirm the actual SQL emitted by SQLAlchemy (including any cascades) before turning this draft into grants.

### Review status

- [x] Enumerated route decorators and explicit ORM/raw-SQL write sites across all current router modules, including attendance, timetable and class management.
- [ ] Inspect every query and mutation branch, not only the route entry point.
- [ ] Inspect all model relationships, cascades, generated keys and sequence usage.
- [ ] Confirm whether candidate UPDATE privileges are truly needed on fee structures, subjects, invoices and any other uncertain table.
- [ ] Confirm auth bootstrap and activation lookups can be moved to Supabase Auth Admin API.
- [ ] Test each command under a no-BYPASSRLS staging role with tenant and role-negative cases.
- [ ] Generate least-privilege grants only after the above review.


## New school operations tables — 5 November 2026

The following proposed tables are now represented in API models and routers. Their SQL remains in `supabase/proposed_migrations/` and has not been applied. These are candidate API-runtime privileges only; do not grant them until the no-BYPASSRLS runtime design is implemented and validated.

| Table | Candidate API operations | Scope / notes |
|---|---|---|
| `attendance_sessions` | SELECT, INSERT, UPDATE | School-scoped daily class registers; submitted registers are immutable through API. |
| `attendance_records` | SELECT, INSERT, UPDATE | School, session and student are bound by composite foreign keys; status changes only while session is draft. |
| `timetable_entries` | SELECT, INSERT, DELETE | School-scoped term/class periods; only owner/headmaster create/remove; teacher reads are assignment-scoped. |
| `class_teacher_assignments` | SELECT, INSERT, UPDATE | School-scoped teacher/class assignments; soft removal via `is_active`, no hard delete route. |

New model-level composite unique keys on `users(school_id,id)`, `students(school_id,id)`, `terms(school_id,id)` and `subjects(school_id,id)` support same-school composite foreign keys. The corresponding constraints are staging-only proposals, not live database guarantees yet.

Teacher authorization now depends on `class_teacher_assignments`: student directory reads/lookups, mark entry and attendance are limited to assigned classes; timetable reads are limited to assigned classes or periods assigned directly to the teacher. A teacher without assignments receives no class roster. Class names currently derive from `students.form`; a normalized class catalogue remains future work.


## Platform identity separation hardening — 5 November 2026

The shared `require_supabase_roles(...)` dependency now rejects every `is_admin` principal instead of treating the legacy admin flag as a blanket role bypass. School workflows require a non-admin, school-scoped role explicitly listed by the endpoint. Vortex platform operations must use the dedicated `/platform/*` permission checks; the one cross-school Paynow reconciliation endpoint independently requires `principal.is_platform_admin`. This prevents a platform identity or a mismatched legacy admin flag from inheriting school-owner, bursar, teacher or student permissions through shared dependencies.
