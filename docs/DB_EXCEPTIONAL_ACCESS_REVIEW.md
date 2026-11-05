# Exceptional database access review

**Status:** source-level security review; proposal only. No production SQL, grants, credentials or Render settings changed.  
**Reviewed:** 5 November 2026  
**Branch:** `work/migration-and-financial-hardening-20261105`

## Why this review exists

Most API routes receive a verified `SupabasePrincipal`, but a small set of endpoints deliberately runs before a normal school principal exists or without a user bearer token. These flows cannot safely inherit a generic tenant policy or a broad platform bypass. They need separate request classification, narrowly bounded SQL access and dedicated negative tests.

## 1. First Vortex owner bootstrap — `POST /auth/bootstrap-admin`

Observed operations:
- Takes a dedicated `X-Chikoro-Bootstrap-Token` header; no Supabase bearer principal is required.
- Locks `public.profiles` in EXCLUSIVE mode and checks that no `vortex_admin` profile exists.
- Reads one configured active local admin row from `public.users`.
- Reads a confirmed matching identity from `auth.users`.
- Inserts the `vortex_admin` profile link and commits.

Security boundary:
- Keep this as a one-time operator-controlled action, not a general RLS policy for all requests.
- Do not give the ordinary runtime role unrestricted access to `auth.users` or table-level access to lock all profiles.
- Prefer a deployment/operator-only bootstrap procedure with a short-lived one-time credential and explicit audit trail. If implemented through a database function, it must be private-schema, tightly owned, fixed-search-path, input-validated, and not executable by PUBLIC; avoid SECURITY DEFINER unless its full privilege boundary has been independently reviewed.
- The owner identity must be verified through Supabase Auth Admin API or an equivalent trusted operator path. Never link an identity merely because an email appears in request data.
- Preserve the existing exact-one-active-owner checks and make the operation safely repeatable only as a rejected no-op after success.

## 2. Student and parent activation — `POST /auth/student/activate`, `POST /auth/parent/activate`

Observed operations:
- Verify the Supabase JWT in FastAPI, then query `auth.users` for the verified subject's email and confirmed-email timestamp.
- Read failed-attempt counters from `public.audit_logs`.
- Parent activation locks matching `public.contacts` rows joined to same-school `public.students`; validates the hashed PIN; reads/creates `public.users`; reads/writes `public.profiles`; upserts `public.guardian_links`; updates contact activation fields; appends an audit event.
- Student activation reads the local user and candidate student, validates the hashed PIN, reads/writes `public.profiles`; updates student activation fields; appends an audit event.
- Both flows commit during the request and must be treated as pre-tenant-context until a unique, valid school/student/contact match is established.

Security boundary:
- Do not set a school or parent/student role from request payload.
- The only initial trusted context is the verified Auth subject. A verified email is a matching attribute, not sufficient authorization by itself; the school-issued one-time PIN and exact school/student/contact relationship remain required.
- Prefer an Auth Admin API lookup for the verified user record so the runtime role does not need `auth.users` privileges. The current implementation needs the Auth secret key to use the admin API; that secret must remain server-side and must be configured and tested before replacing the current lookup.
- Rate-limit by a non-reversible identifier and source/network controls. The current failed-attempt counter is recorded in audit logs; ensure concurrent attempts cannot race past the threshold and consider a dedicated activation-attempt table with a unique time-bucket key if rate limiting is expanded.
- RLS policy for activation must be distinct from ordinary student/parent portal policies. It must not allow a user to enumerate contacts or students by email or PIN.
- Add tests for duplicate email/contact matches, duplicate local-user mappings, expired/replayed PINs, cross-school contacts, inactive students, already-linked Auth IDs and multiple commits/rollback.

## 3. Paynow provider callback — `POST /paynow/webhook`

Observed operations:
- No Supabase bearer principal; parses provider callback form fields.
- Looks up one `public.paynow_attempts` row by merchant reference, or exact stored polling URL.
- Reads the corresponding `public.schools` payment configuration.
- Calls the provider polling endpoint and verifies signed response/reference before any payment settlement.
- May update the attempt, then create `payments`, `payment_allocations` and `receipts` through the shared verified-settlement helper.

Security boundary:
- Callback form fields are only lookup hints; never trust their payment status, amount, currency, school or learner fields.
- A callback must never create a payment unless the provider poll is signed, the reference matches the stored attempt, the amount/currency match, and the invoice balance is rechecked under the documented lock order.
- Restrict lookup to exact stored references/URLs; keep strict outbound host validation and redirect refusal.
- Apply request-size limits, bounded form parsing, per-IP/provider rate limits and request timeouts. Avoid logging full polling URLs or integration credentials.
- Consider a separate database identity or a narrow callback-specific stored procedure that can access only one attempt and its linked school/invoice rows. Do not grant this unauthenticated route cross-school SELECT/UPDATE over all payment tables.
- Test unknown references, forged callback statuses, forged poll URLs, mismatched provider references, bad hashes, duplicate callbacks, late cancellation after settlement, and concurrent settlement.

## 4. Paynow reconciliation — `POST /paynow/reconcile`

Observed operations:
- Requires a platform admin principal at application level.
- Scans `sent` and `unverified` attempts across schools with `FOR UPDATE SKIP LOCKED`.
- Reads each school's Paynow integration configuration and performs provider polling; verified results can settle payments.

Security boundary:
- This is a cross-school system operation, not a school-tenant query.
- Keep it unavailable to school owners, headmasters and bursars even if they can call the route; the existing route-level admin-only check must be preserved and tested.
- Prefer a dedicated scheduled worker identity with explicit platform reconciliation permissions once a real worker is introduced. The current worker is only a placeholder.
- Do not give the normal request runtime a blanket cross-school payment policy solely to support reconciliation.

## 5. Notifications processing — `POST /notifications/process`

Observed operations:
- Requires owner/headmaster application role.
- Selects queued notifications and marks them sent; current code contains a placeholder and does not deliver messages.
- For non-platform users it scopes the query to the principal's school; the platform-admin path can scan all schools.

Security boundary and product correctness:
- Preserve school scoping for ordinary school users.
- Do not give the runtime cross-school notification access because of the platform-admin branch; if platform-wide processing is needed, move it to a dedicated worker.
- Do not represent the current endpoint as actual email/SMS delivery. It currently changes status to `sent` without invoking a delivery provider. Before launch, either implement real provider delivery with retry/idempotency or rename the state transition to a clearly non-delivery status and test it.

## Required release gates

- [ ] Decide whether bootstrap is an operator tool or a separately privileged database action; remove it from generic runtime policy scope.
- [ ] Replace direct `auth.users` reads with a verified Auth Admin API lookup, or approve a narrowly scoped alternative after inspecting exact required columns and grants.
- [ ] Define separate request kinds for activation, ordinary authenticated school traffic, platform staff, provider callback and reconciliation.
- [ ] Ensure no request payload can select or elevate its request kind.
- [ ] Verify context is re-established after each SQLAlchemy transaction restart and cleared on pool return.
- [ ] Add positive and negative tests for each exceptional flow, including cross-school attempts and concurrency.
- [ ] Run the complete API test suite and staging integration suite under a role with `BYPASSRLS = false`.
- [ ] Do not change the production Render database identity until all gates pass and rollback is rehearsed.

## Current decision

No policy or grant SQL is approved by this document. Keep production on its existing connection until a staging clone proves the ordinary and exceptional request paths work under a dedicated non-bypass runtime role.
