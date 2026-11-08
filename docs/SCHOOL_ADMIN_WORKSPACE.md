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

## Teacher workspace

Teacher sign-ins route to `/school-admin/teacher`. The workspace lists school learners, terms, subjects and assessments; teachers can create subjects and assessments and submit bulk learner marks as drafts. Only owners and headmasters can approve and publish marks. Teachers can read their own school's terms but cannot request another school's terms.

## Class management and teacher assignments

Owners and headmasters can use `/school-admin/classes` to view active class groups (derived from learner form/class values), assign active school teachers to a class, and remove assignments. Teachers see only their own assigned classes and assignments. The API now limits teacher learner-directory reads and individual learner lookups to assigned classes, blocks teacher learner creation, limits mark entry to assigned classes, and restricts attendance registers to assigned classes. Teachers see timetable entries for their assigned classes or periods assigned directly to them. This closes the earlier school-wide teacher visibility gap; class-level authorization is now the default.

The assignment table is in `supabase/proposed_migrations/20261105_add_class_teacher_assignments.sql` only and has not been applied. Until this migration is validated in staging, teacher-facing class and attendance workflows remain gated from production release.

## Timetable workspace

Owners and headmasters can manage the weekly timetable at `/school-admin/timetable`; teachers have read-only access. Entries are scoped to a school and academic term and include class/form, subject, optional teacher, weekday, period number, start/end time and room. The API rejects overlapping class, assigned-teacher or room bookings, validates teacher/subject/term membership, and records create/delete audit events. A school row lock serializes timetable writes before conflict checks. The database enforces one period number per class/day/term and composite foreign keys keep terms, subjects and assigned teachers within the school.

The timetable schema is in `supabase/proposed_migrations/20261105_add_timetable_entries.sql` only. It has not been applied. It must pass staging migration, RLS/grant and end-to-end checks before the timetable API is released.

## Attendance workspace

Owners, headmasters and teachers can use `/school-admin/attendance` to create one daily register per class/form, mark active learners present, absent, late or excused, add optional notes, save a draft, and submit a complete register. Submission requires every active learner in the selected class to have a status; submitted registers are read-only. The API checks the school and class on every learner, rejects duplicate learners and duplicate class/date registers, and writes audit events. There is no teacher-to-class assignment model yet, so teacher access is currently limited to their own school rather than a particular assigned class.

The attendance tables are defined in `supabase/proposed_migrations/20261105_add_attendance_registers.sql` only. They are not in the applied migration directory and have not been run against staging or production. The attendance API must not be released until the migration has been reviewed and applied in a disposable/staging environment, RLS and grants are verified, and end-to-end tests pass.

## Academic management workspace

Owners and headmasters can use `/school-admin/academics` to create academic terms, review marks submitted by teachers, approve drafts, and publish approved marks. The API exposes a tenant-scoped mark review endpoint; teachers can see only marks they personally entered, while owners/headmasters can review all marks in their school. Teacher mark entry remains draft-only. Only owners/headmasters can approve and publish results.

## Finance workspace

The `/school-admin/finance` page is available to school owners, headmasters and bursars. It reads only the authenticated school's learner, invoice and payment records. It shows open invoices, balances by currency, and recent payments; authorized staff can record a manual cash, bank or mobile-money payment. Allocation, overpayment prevention, duplicate-reference checks and receipt numbering are enforced by the API. The page does not directly initiate Paynow transactions.

Bursar sign-ins route directly to the finance workspace. Bursars are not granted access to the owner/headmaster staff directory or school overview.

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
