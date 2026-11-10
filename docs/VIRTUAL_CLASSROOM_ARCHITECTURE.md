# Virtual classroom architecture (proposal)

Status: design only. No production deployment or database migration authorized by this document.

## Scope
Secondary schools, colleges and polytechnics. Institution admins may allow embedded meetings, external meeting links, or both. No university-specific workflows in the initial release.

## Design principles
- Chikoro remains the source of truth for institutions, enrolments, assignments, schedules and attendance.
- Video media is handled by a dedicated provider, never by the FastAPI application or Vercel frontend.
- Provider adapters separate embedded Jitsi-compatible meetings from external Google Meet, Zoom, Teams and Jitsi links.
- No classroom may be accessed merely by knowing a session ID or URL.
- Institution admins configure provider allow-lists; platform operators do not receive implicit access to live classes.
- Start with no recording; enable only after consent, retention, encryption, storage cost and access policies are approved.

## Proposed data model (not yet migrated)
- classroom_provider_settings: institution_id, allowed_modes, approved_domains, recording_policy, configured_by, updated_at.
- classroom_sessions: id, institution_id, course_or_class_id, host_user_id, provider, mode, starts_at, ends_at, status, external_url_encrypted_or_reference, created_at.
- classroom_participants: session_id, institution_id, user_id, enrollment_id, role, join_authorization_state.
- classroom_attendance_events: id, session_id, institution_id, user_id, provider_event_id, event_type, occurred_at, source, verification_state.
- classroom_audit_events: id, institution_id, session_id, actor_user_id, action, occurred_at.

Adapt institution_id to the repository's existing school_id tenancy key rather than creating a competing tenant model. Foreign keys must enforce same-institution relationships. Add unique indexes for provider event idempotency.

## API contract (proposal)
- POST /classrooms: create a session (assigned teacher/lecturer only)
- GET /classrooms: list only sessions visible to the principal's institution and enrolments
- POST /classrooms/{id}/start: recheck host assignment and issue provider credentials
- POST /classrooms/{id}/join: recheck active enrolment, session state and identity; return short-lived embedded join token or approved external URL
- POST /classrooms/{id}/end: host or authorized admin closes session
- POST /classrooms/provider-events/{provider}: verify webhook signature, deduplicate and reconcile attendance

All routes must derive tenant and role from verified Supabase identity, never from request body. Use rate limiting and audit events on session creation, joining and provider callbacks.

## External-link security
Only HTTPS URLs on explicitly approved hostnames; normalize and validate URL parsing and reject credentials, redirects to unapproved domains and unsafe schemes. External attendance is *unverified* unless authenticated provider events are available. Do not imply that a link alone enforces enrolment-based access.

## Embedded provider
Evaluate managed Jitsi-compatible or other hosted SDK providers for authentication, moderation, mobile browser support, concurrency and cost. Public free meeting endpoints are not an assumed production SLA.

## Required tests
1. Two-institution isolation for create, list, start, join, end, events and recordings.
2. Student not enrolled, deactivated user, removed teacher assignment and expired token all denied.
3. Concurrent join/start, duplicate callbacks, out-of-order leave/join, reconnects and clock skew.
4. Malicious external URL, redirect and webhook signature rejection.
5. Attendance reconciles correctly with absent or unreliable provider events.
6. Browser/mobile compatibility, bandwidth degradation, load and failure recovery.
7. Recording access, retention and deletion tests if recording is enabled.

## Release gates
Do not merge or deploy classroom APIs until staging migrations, RLS, API auth, provider credentials, load tests and privacy review are complete. Keep financial/security PR #2 independent of this feature branch.

## Delivery slices
A. Schema and RLS proposal with tests; B. scheduling and provider settings; C. embedded adapter; D. external link adapter; E. attendance and reporting; F. pilot and release validation.
