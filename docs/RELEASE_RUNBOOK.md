# Chikoro Digital coordinated release runbook

**Status:** preparation only. This document does not trigger a deployment or authorize production database changes by itself.

## Current deployment topology

| Component | Current evidence | Release handling |
|---|---|---|
| Supabase PostgreSQL/Auth | Project `xivzduvqpuqbecskxaoj`; four canonical migrations are recorded as already applied | Verify migration ledger and backup/restore path; apply only reviewed forward migrations in the approved order. |
| FastAPI API | Render service `Chikoro-Digital`, service ID `srv-dbifhi49v7es739svs7g`, root `api`, production branch `main`, auto-deploy enabled | Deploy after compatible DB changes and environment readiness. Verify live commit and health/smoke tests. |
| Staff/student/parent web app | Vercel project linked to the same GitHub repository | Reconfirm production project ID, root directory, domains and production branch before release. |
| Vortex developer/admin portal | Separate Vercel project linked to the same repository | Reconfirm production project ID, root directory, domains and production branch before release. |
| Additional Vercel projects | Four Vercel projects are linked to this repository; the remaining project purposes and deployment roots need a fresh inventory | Do not assume every linked project should receive every frontend build. Map each project to its application and environment first. |
| Background worker | `worker/worker.py` is currently a placeholder; no production job-processing implementation has been verified | Do not deploy or grant database access to a worker until actual jobs, service configuration and permissions are ready. |
| Mobile apps | Current repository inventory reviewed here identifies the web portals; native iOS/Android release artifacts have not been verified | Treat App Store / Google Play publishing as a separate release stream once native or approved installable app packages exist. |

## Required release sequence

1. **Freeze and identify the release**
   - Confirm the target commit and compare it with production `main`.
   - Confirm the release scope: API, staff web, Vortex portal, database migrations, worker (if implemented), and any mobile artifacts.
   - Check that no unrelated or experimental work is included.
2. **Pre-release verification**
   - Run the full GitHub Actions suite: API tests, web build, admin build.
   - Confirm Vercel build quota and required project environment variables.
   - Confirm Render environment variables, health endpoint, database connectivity and rollback connection.
   - Confirm Supabase backup/restore readiness and review all migration statements.
3. **Database phase**
   - Reconcile migration ledger with repository history.
   - Apply only approved, forward-only migrations in dependency order.
   - Verify constraints, policies, indexes, grants and migration ledger immediately after each migration.
   - Never deploy a schema change that the currently live API cannot tolerate.
4. **API phase**
   - Deploy the approved API commit to Render.
   - Verify the actual live deployment SHA, startup logs, health endpoint, auth resolution, tenant isolation, financial endpoints and webhook behavior.
   - If the runtime DB role changes, verify the live connection identity and RLS behavior before proceeding.
5. **Frontend phase**
   - Deploy the staff/student/parent web project and Vortex developer portal to their correct Vercel projects.
   - Deploy any other linked project only if its purpose and release scope are confirmed.
   - Verify each project's deployment SHA, domains, environment and API base URL.
6. **End-to-end smoke tests**
   - Sign in as a school owner, headmaster, bursar, teacher, student, parent and Vortex operator where test identities exist.
   - Verify school scoping, student/guardian linking, published results, fee status, manual payments, Paynow test checkout, webhook verification, receipt generation and audit logs.
   - Confirm cross-school and cross-student negative cases remain blocked.
7. **Closeout**
   - Record all deployment IDs, commit SHAs, migration versions, test outcomes and any known limitations.
   - Keep the previous API deployment/connection details available for rollback.
   - Do not mark the release complete until every in-scope component is verified.

## Production auto-deploy safety

Render auto-deploys from `main`. Do not push incomplete changes to `main`. Prepare and validate work on a feature branch, then coordinate the merge/release window so the database and API changes remain compatible. Render's preview services are currently disabled, so a feature branch does not create a Render preview deployment.

Vercel may create preview deployments for pull requests/branches. On 5 November 2026, the Vercel integration returned `Deployment rate limited — retry in 24 hours` for the four linked projects on this review branch. These were preview/status checks, not production releases. Recheck quota before the next preview or production release; do not repeatedly retry while rate-limited.

## Explicit non-goals until separately ready

- Do not apply the staging-only profile role or financial uniqueness proposals to production before staging validation and migration review.
- Do not change Render's database connection away from `postgres` until the no-BYPASSRLS role and tenant RLS policies pass staging tests.
- Do not enable platform owner bootstrap, staff invitations or secrets until the role migration and required environment settings are verified.
- Do not deploy the placeholder worker as a production processor.
- Do not claim App Store / Google Play availability until actual store builds are produced, tested and published.

## Release completion record

Fill this in during the actual release:

- Release commit:
- Supabase migration versions applied:
- Render deployment ID / commit:
- Vercel project → deployment ID / commit:
- Worker deployment (if in scope):
- Smoke test result:
- Rollback decision / notes:
- Release completed at:
