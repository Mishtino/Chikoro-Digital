# Chikoro Digital RLS policy design — staging proposal

**Status:** design proposal only. No live policies, grants, roles or database objects were changed.  
**Reviewed:** 5 November 2026  
**Branch:** work/migration-and-financial-hardening-20261105

## Why a policy design is needed

The live database has RLS enabled on all 21 public base tables, but the only policy currently present is the authenticated user's own-profile SELECT policy on public.profiles. The other 20 public tables have no policies. The Render API currently uses postgres with BYPASSRLS = true, so its SQL bypasses those policies.

A non-bypass API role cannot be switched in until the application has a reliable tenant context and every required route has a matching policy. Simply enabling RLS or adding a broad allow-all policy would either break the application or remove the security benefit.

## Proposed request context

After verifying the Supabase access token and resolving the trusted public.profiles / public.users mapping, the API should attach these server-derived values to its SQLAlchemy Session:

- app.auth_user_id: verified Supabase Auth UUID.
- app.local_user_id: local public.users.id.
- app.school_id: resolved school ID, empty for Vortex platform staff.
- app.role: trusted profile role, never a value copied from request JSON or user-editable metadata.
- app.is_platform_admin: true only for the verified Vortex platform administrator identity.
- app.request_kind: a narrow server-selected request category for exceptional flows such as activation or provider callbacks.

Use parameterized set_config(..., true) to set transaction-local values. Reapply them at every SQLAlchemy transaction begin because application routes commit multiple times in a request. Ensure exception/rollback/connection-pool paths cannot leak one request's context into another. The request context must be set only by trusted server code after token verification.

**Important limitation:** custom PostgreSQL settings are not cryptographically protected from arbitrary SQL executed as the same database role. RLS context is a valuable defense against accidental unscoped queries and application bugs, but it does not replace parameterized SQL, input validation, safe query construction, or application authorization. Do not claim this mechanism alone defeats SQL injection.

## Proposed table policy matrix

This is a starting policy map, not executable SQL. Exact read/write operations must be reconciled with DB_ACCESS_MATRIX.md before implementation.

| Table | Tenant key / relationship | Proposed policy boundary |
|---|---|---|
| schools | id | School users may read their own school; only verified Vortex platform admin may create/update/suspend schools; platform support may read directory data only. |
| users | school_id, id | School admins may read users in their school; users may read their own minimum profile; platform staff may read only the platform staff directory; no cross-school user access. |
| profiles | id, local_user_id, school_id | Preserve authenticated own-profile SELECT; trusted activation/bootstrap/staff lifecycle paths get narrowly scoped writes; school users cannot enumerate unrelated Auth identities. |
| students | school_id, portal_user_id | School staff only within their school; student portal reads only its unique linked active learner; parent access must be mediated by verified active guardian link. |
| contacts | school_id, student_id | School staff only within school; parent sees only linked contact/learner context; activation path may find only the matching email/PIN record and must rate-limit. |
| guardian_links | school_id, profile_id, contact_id | A parent sees only its own verified active links; school staff manage only links in their school; no direct client-controlled link creation. |
| terms | school_id | School staff read/write own school; student/parent portal reads only terms associated with published results or relevant fee records. |
| fee_items | school_id | School staff only within school; student/parent read only the fee details needed for their own fee status. |
| fee_structures | school_id, term_id | School staff only within school; portal access only through scoped invoice/fee endpoints. |
| fee_structure_items | school_id, fee_structure_id | Enforce school scope and verify the parent structure belongs to the same school. |
| invoices | school_id, student_id | School bursar/admin within school; student only own invoices; parent only invoices for a verified linked learner. |
| invoice_lines | school_id, invoice_id | Same visibility as parent invoice; require the referenced invoice to match school and student context. |
| payments | school_id, student_id | School bursar/admin within school; student/parent only own/verified linked learner payment summaries; platform access only by explicit billing permissions if later implemented. |
| payment_allocations | school_id, payment_id, invoice_id | Enforce same-school payment and invoice relationships; no client-side direct writes; preserve cross-student allocation checks. |
| receipts | school_id, payment_id | School staff within school; student/parent only receipts for own/verified linked learner; enforce referenced payment tenant. |
| paynow_attempts | school_id, student_id, invoice_id | School staff within school; student/parent only own checkout attempts; provider callback/reconciliation need a separate, narrowly scoped server-only path. |
| subjects | school_id | School staff within school; portal read only when required to display published results for linked learner. |
| assessments | school_id, subject_id, term_id | School staff within school; portal reads only assessments with published marks for linked learner. |
| marks | school_id, student_id, assessment_id | Teachers/admin within school for authorized write workflows; student/parent only published marks for own/verified linked learner. |
| audit_logs | school_id, actor_user_id | School admins see own school audit entries; Vortex auditor/admin only through explicit audit permission; inserts server-side only; no ordinary updates/deletes. |
| notifications | school_id | School-scoped notification visibility; only trusted server components create/update delivery state; worker gets a separate narrow role if implemented. |

## Exceptional flows requiring separate treatment

1. **Supabase Auth user creation trigger:** auth.users INSERT fires private.handle_new_auth_user(), a SECURITY DEFINER trigger function owned by postgres that inserts a pending public.profiles row. Keep this trigger's owner and private schema access separate from the runtime role. Do not grant the API execute or private schema privileges.
2. **Student/parent activation:** these endpoints verify a bearer token and look up auth.users before a school link is resolved. They need a deliberately designed identity lookup path and must not gain broad access to auth.users.
3. **Paynow webhook:** callback requests are provider-originated and do not carry a Supabase user JWT. The current endpoint locates a stored attempt using a merchant reference, then verifies provider response hash and polls Paynow. Design a separate restricted callback path or carefully bounded lookup so an unauthenticated caller cannot read attempts or mutate arbitrary tenant records.
4. **Paynow reconciliation:** the owner-only job scans attempts across schools. It needs an explicit platform/system permission, not a generic tenant bypass.
5. **Vortex platform staff:** Vortex admin/support/auditor roles are tenant-free and must not inherit school-user access. Their cross-school access must be limited by exact platform permissions.
6. **Bootstrap:** first-owner bootstrap is a one-time controlled operation and should not become a standing unrestricted global database policy.

## Transaction lifecycle requirements

- Set context after verified principal resolution and before protected application queries.
- Ensure the context is reapplied after every commit begins a new transaction.
- Handle endpoints that verify a token manually instead of using get_supabase_principal.
- Use explicit request-kind allowlists for webhooks and activation; never let request bodies select a privileged context.
- Clear or invalidate Session context before returning the connection to the pool; verify this behavior under exceptions and rollback.
- Add tests proving a request with school A context cannot see or mutate school B rows, even after commit/rollback boundaries.

## Staging implementation gates

- [ ] Finalize CRUD/sequence matrix for every route and raw SQL statement.
- [ ] Design and peer-review helper expressions and policy SQL.
- [ ] Build staging clone with representative school, user, guardian, student, invoice, payment, result and audit data.
- [ ] Implement transaction context in a feature branch and prove it survives multiple commits without cross-request leakage.
- [ ] Add policies table-by-table with negative cross-school, cross-student and unverified-parent tests.
- [ ] Exercise webhook and reconciliation under the restricted role.
- [ ] Verify role has BYPASSRLS = false, no elevated membership, no schema CREATE, no ownership and no access to unrelated Auth/private objects.
- [ ] Run full API, web and admin CI plus Supabase Security Advisor.
- [ ] Only after all checks pass, prepare a backward-compatible migration and controlled Render connection cutover.

## Release gate

Do not apply this design to production or change Render's database connection until staging passes and the complete migration and rollback plan is reviewed. See DB_LEAST_PRIVILEGE_PLAN.md, DB_ACCESS_MATRIX.md and RELEASE_RUNBOOK.md.
