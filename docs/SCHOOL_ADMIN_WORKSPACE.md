# School administration workspace

## Entry point

School owners and headmasters with an active, school-scoped Supabase profile are routed to `/school-admin` after sign-in. The page obtains the authenticated identity from `/auth/supabase/me` and loads `GET /school-admin/overview`. The API derives the school exclusively from the verified principal; callers cannot select another school.

The overview returns:
- school name, code, province, status and plan
- total, active and inactive learners
- active and disabled school staff
- current academic term, subject and assessment counts
- draft, approved and published mark counts
- open invoice count and outstanding balances grouped by currency

The finance summary excludes void invoices and allocations from voided payments. It is read-only and is not a substitute for invoice-level finance permissions.

## Learner management

The `/school-admin/students` page supports:
- registering learners with an optional learner portal email and guardian contact details
- school-scoped learner search and active/inactive filtering
- editing first name, last name and form
- issuing a fresh activation PIN only when a portal account is linked and the learner is not yet activated

Activation PINs are shown once in the current page response. Operators must deliver them through a secure channel; the page does not persist them. The API directory returns a boolean `portal_enabled` value, never a learner email address.

## Staff management

The `/school-admin/staff` page supports a school-scoped directory. Invitation controls are shown only when the API reports that all readiness checks pass. Staff invitation creation remains disabled by default via `SCHOOL_STAFF_INVITATIONS_ENABLED=false`.

Role and active/inactive status controls are separately gated by `SCHOOL_STAFF_LIFECYCLE_ENABLED=false`. Their API routes enforce the owner/headmaster role matrix and require consistent local-user/profile links. Inactive profiles are denied by the API principal resolver.

## Outstanding work and release gates

- Add full student lifecycle controls (transfer, withdrawal, archival) with school policy and audit coverage.
- Add class/form configuration, attendance, timetable and teacher workspaces.
- Add end-to-end tests against a staging Supabase Auth project for learner and staff activation.
- Verify email delivery, rate limits, Auth redirect URLs and secret availability before enabling invitations.
- Validate all new endpoints against a least-privilege API database role and tenant RLS design.
- Keep production deployment and migrations disabled until staging checks and explicit release approval.

This workspace is under active development. Passing CI does not mean production activation is approved.
