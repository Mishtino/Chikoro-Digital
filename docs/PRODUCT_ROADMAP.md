# Chikoro Digital Product Roadmap

## Product vision
A secure, multi-tenant school management and digital learning platform operated by Vortex Technologies. The platform has three distinct experiences: Student & Parent Portal, School Administration Portal, and Vortex Global Administration.

## Non-negotiable platform principles
- Supabase Auth is the single identity provider for every human user.
- FastAPI verifies Supabase access tokens and enforces role, school, ownership, and active-account checks on every protected operation.
- School data is tenant-isolated. A school administrator must never access another school's records.
- The Next.js browser uses only the Supabase publishable key. Service-role/secret keys remain server-side only.
- RLS is enabled on every exposed public table. Direct browser access is granted only where a reviewed, tested per-table policy requires it.
- Financial operations, payment callbacks, privileged provisioning, audit events, and cross-tenant administration remain backend-only.
- No user can grant themselves a role, school assignment, guardian relationship, or elevated permission.
- Every privileged action is attributable, logged, and reviewable.
- Build mobile-first, accessible interfaces and test small screens before release.

## Experience A — Student & Parent Portal

### Student workspace
- Personal dashboard: school, class, term, attendance, upcoming deadlines, announcements.
- Academic record: subject marks, grades, teacher feedback, term comparisons, downloadable report cards.
- Timetable and school calendar.
- Assignments: instructions, due dates, attachments, submissions and feedback.
- Learning resources: subject folders, notes and revision material.
- Attendance history and authorised absence explanations.
- Fee statement, payment history, receipts and Paynow checkout.
- Profile and secure account settings.

### Parent workspace
- One account can link to multiple verified learners.
- Attendance history and summaries now have a backend endpoint and parent dashboard view. Only submitted registers for active, verified linked learners are returned; date filters are supported and the summary counts the full matching history while the visible register is capped at the latest 100 records.
- Per-child overview with clear learner switching.
- Attendance and absence alerts.
- Results, report cards and teacher feedback.
- Fee balances, itemised statements, receipts and secure payments.
- School announcements, event calendar and teacher-school communication.
- Guardian relationships require verified email and school-issued, one-time activation credentials.

### Portal release gates
- Parent attendance visibility is implemented on the feature branch and must pass API/UI CI plus staging tenant-isolation tests before release.
- Never expose another learner's data by changing a URL or request identifier.
- Parent access is derived only from active, verified guardian links.
- Student access is restricted to the authenticated student's own record.
- Notifications must not disclose sensitive student details on lock screens by default.

## Experience B — School Administration Portal

### School leadership
- School overview with enrolment, attendance, academic and fee-collection indicators.
- Student admissions, enrolment, transfers, class and stream allocation.
- Staff directory, invitations, role assignment and deactivation.
- Class, subject, academic year, term and grading configuration.
- Timetables and school calendar.
- Announcements and controlled parent communications.
- Operational and statutory reports with PDF/Excel exports.

### Teaching workspace
- Assigned classes and subjects only.
- Attendance capture and correction history.
- Assessment entry, moderation/approval and report-card publishing.
- Assignment creation, resources and feedback.
- Class performance analytics.

### Bursar and finance workspace
- Fee structures and student invoices.
- Payment recording with audit trail.
- Paynow transaction reconciliation and callback verification.
- Receipts, balances, arrears and reminders.
- Daily/monthly collection reports and exportable ledgers.
- Separation of duties for recording, reversing and reconciling payments.

### Additional school modules
- Library catalogue, circulation and overdue tracking.
- Inventory/assets, stock movements and low-stock alerts.
- School events and examination calendar.

### School administration release gates
- Every record and query is scoped to the authenticated user's school.
- Staff permissions are least-privilege and configurable only by authorised school leadership.
- Financial reversals and sensitive changes require reason capture and immutable audit events.
- Bulk imports are validated, previewed and reversible before commit.

## Experience C — Vortex Global Administration

### Platform command centre
- Global dashboard: active schools, learners, staff, parents, growth and platform health.
- School onboarding, approval, configuration, suspension and reactivation.
- Tenant-level usage and feature entitlements.
- Platform user support and account lifecycle management.
- Subscription plans, billing, renewals, invoices and payment status.
- Platform-wide announcements and service notices.
- Support tickets, diagnostics and controlled escalation.
- API, database, frontend, queue and payment integration health.
- Security centre: privileged activity, failed login trends and security alerts.
- Immutable audit search and export.
- Feature flags and staged rollout by school or plan.

### Commercial model
- Configurable Starter, Standard, Premium and Enterprise plans.
- Entitlements and usage limits must be enforced server-side, not merely hidden in the UI.
- Subscription status changes must have an audit record and clear grace-period rules.
- Revenue metrics must reconcile to verified payment records, not just invoice totals.

### Vortex access safeguards
- Global administration is a distinct platform role, never a school role.
- Cross-tenant access is explicit, justified, scoped and audited.
- Support impersonation is not a default capability. If introduced, it must be time-limited, approved, visible and fully audited.
- Platform-wide actions require confirmation and record actor, reason, target and outcome.

## Shared platform capabilities
- Unified Supabase authentication and verified email lifecycle.
- Role- and permission-aware navigation.
- Notification centre with email/SMS/push channels added progressively.
- Search with server-side permission filtering.
- Activity history and audit trail.
- Document storage with private buckets and signed, short-lived access.
- CSV/XLSX/PDF import and export with permission checks.
- Responsive, accessible design and low-bandwidth-friendly pages.
- Localised currency, dates, school terms and Zimbabwe-specific payment workflows.
- Backup, restore and retention procedures.
- Monitoring, structured logs, error tracking and operational alerts.

## Delivery sequence

### Foundation and release safety
1. Complete unified authentication, verified admin identity and secure staff invitations.
2. Test tenant isolation and role enforcement across every API route.
3. Keep public Data API access deny-by-default; introduce only narrow, tested RLS grants.
4. Establish migrations, automated tests, CI checks, deployment health checks and rollback procedures.
5. Finish and test the three portal authentication experiences.

### Core school operations
6. Student records, classes, subjects, staff and attendance.
7. Fees, invoices, payments, receipts and reconciliation.
8. Examinations, grading, report cards and academic analytics.
9. Parent/student dashboards, timetables, assignments and learning materials.

### Platform operations and growth
10. Vortex global command centre, onboarding and support.
11. Subscription plans, billing and entitlements.
12. Notifications, library, inventory and advanced analytics.
13. Mobile app/PWA enhancements and integrations.

## Definition of done for every module
- Requirements and role matrix documented.
- Backend validation and authorization implemented.
- Tenant-isolation tests cover both allowed and denied cases.
- UI is responsive, accessible, and handles loading/empty/error/success states.
- Audit events exist for privileged or financial mutations.
- Automated tests and CI pass.
- Migration is reviewed and reversible where practical.
- Production rollout is monitored and has a rollback plan.
