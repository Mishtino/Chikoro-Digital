# School staff onboarding and account lifecycle

## Status

Design and release-gate document. The school staff directory is read-only today. Local-password creation at `POST /users` remains disabled (HTTP 410). No staff invitations, role changes, or deactivations are performed by this document.

## Required identity model

- Supabase Auth owns credentials, email verification, recovery, and sessions.
- `public.profiles` is the authoritative link from the Supabase UUID to one local user, role, school, and active state.
- `public.users` remains the application-facing staff record. Do not create a second password-based login path.
- A school staff identity must have exactly one school association. Platform identities remain unscoped and use the Vortex platform role allowlist.
- Email is normalized before lookup and uniqueness checks. Never trust a requested school ID or role without deriving the caller's authority server-side.

## Invitation workflow (implemented behind a disabled feature gate)

1. Authenticate the caller and resolve the current profile from the verified Supabase token.
2. Permit only an active school `owner` or `headmaster`; bind the target school to the caller's profile. Do not accept a caller-supplied school override.
3. Enforce an explicit role matrix:
   - `owner` may invite `headmaster`, `bursar`, and `teacher`.
   - `headmaster` may invite `bursar` and `teacher`.
   - Neither role may create platform roles, parents, students, or another owner.
4. Validate normalized email, role, school lifecycle state, and duplicate/in-flight invitations before calling Supabase Auth Admin.
5. Use a server-side Supabase Auth Admin invitation operation. The API validates the configured Auth origin, disables redirects, and never exposes upstream response bodies. Never accept, store, email, or log a plaintext password or service credential.
6. Create an inactive local user and bind the Auth-trigger-created `pending` profile to the same school and approved role in one database transaction. The unique email and profile linkage constraints prevent duplicate local identities; a failed local transaction attempts to delete the newly invited Auth identity.
7. Record an audit event with actor, school, target identity, role, outcome, and correlation ID. Do not put invitation tokens or secrets in audit details.
8. Return a neutral success response. The invitee must complete Supabase's verified invitation flow before access is granted.

## Role changes (implemented behind a disabled feature gate)

- Re-authorize the actor on every request; do not rely on UI visibility.
- Allow only transitions in the role matrix above. A headmaster cannot promote anyone to owner or headmaster.
- Protect the final active owner of a school from accidental removal/demotion; require a separate verified ownership-transfer workflow.
- The gated role-change endpoint updates the local user and profile in one transaction and writes an audit event containing old and new roles. School reassignment and ownership transfer are not supported.
- The gated status endpoint updates the local user and profile together. Inactive profiles are rejected by the API principal resolver on every request, so existing Supabase sessions cannot access Chikoro after deactivation.
- Never permit school reassignment through a normal role-change endpoint.

## Deactivation and reactivation (implemented behind a disabled feature gate)

- Deactivation sets both the local user and profile inactive and creates an audit record. API authorization checks the active profile on every request, immediately blocking further Chikoro access even if the Supabase session itself remains valid.
- A school administrator may affect only staff in their own school and may not deactivate themselves or the final active owner.
- Reactivation requires a fresh authorization check, an active school, and a consistent existing role/school link; it does not restore an obsolete role or school association.
- Do not delete staff records as a substitute for deactivation; retain the audit history.

## Mandatory release gates

Do not enable the write endpoints until all of the following are verified in a non-production staging environment:

- The live/staging `profiles_role_check` migration is reviewed, applied to staging, and validated against all existing role values.
- The Supabase Auth Admin secret is present only in the server runtime, is not exposed to the browser, and a rotation/revocation procedure is documented.
- The schema supports pending invitations and enforces uniqueness for Auth UUID, local user linkage, and school-scoped identity as appropriate.
- Transaction boundaries and rollback behavior are tested, including Auth invitation success followed by database failure and retry/idempotency behavior.
- Authorization tests cover owner, headmaster, platform admin, support, auditor, student, parent, cross-school, inactive actor, and inactive school cases.
- Audit events are tested for success, failure, denied access, role changes, and deactivation.
- Email delivery, invitation expiry, resend limits, rate limits, and abuse monitoring are configured and tested.
- Staging end-to-end tests prove an invitee can activate and access only the intended school's portal.
- Release owner explicitly approves production migration, configuration, and deployment.

## Current safe behavior

The school invitation endpoint exists but is disabled by default (`SCHOOL_STAFF_INVITATIONS_ENABLED=false`). Role and status lifecycle endpoints also exist but are disabled by default (`SCHOOL_STAFF_LIFECYCLE_ENABLED=false`). They fail closed unless the validated role constraint and their required school/identity checks pass. Invitation additionally requires the server-side Supabase secret and live-school status. If enabled in a reviewed staging environment, it creates an inactive local account and a linked but inactive profile; it does not grant access. A verified-email activation endpoint now activates the local user and profile together and writes an audit event. Staging end-to-end proof, email delivery checks, and release approval are still required before invitations can be enabled. The staff directory remains read-only in the UI, and `POST /users` continues to return HTTP 410.
