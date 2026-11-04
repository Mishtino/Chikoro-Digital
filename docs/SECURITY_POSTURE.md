# Chikoro Digital security posture notes

This is a verified snapshot from the 4 November 2026 review. It records gaps that must be addressed before claiming production database hardening.

## Verified observations

- The connected Supabase database reports the application connection role as `postgres`, with `rolsuper = false` and `rolbypassrls = true`. The API therefore bypasses row-level security when it connects with this role. FastAPI tenant checks remain important, but RLS is not currently an independent backstop for API queries.
- Supabase Security Advisor reports RLS enabled with no policies on 20 public tables. This is fail-closed for browser roles; it is appropriate only while browser clients do not directly query those tables.
- The inspected web and Vortex portal source uses Supabase Auth in the browser and calls FastAPI for application data; no direct Supabase `.from(...)` table queries were found in those frontend files during this review.
- Supabase Auth leaked-password protection is disabled and should be enabled in the Auth security settings.

## Required hardening sequence

1. Inventory every FastAPI table operation, trigger, webhook, and background worker query, including required reads from `auth.users` and `public.profiles`.
2. Design a least-privilege application database role with only the required schema usage, table privileges, sequence privileges, and narrowly scoped access to identity tables. Do not store credentials in source control or browser environment variables.
3. Test the API, workers, payment callbacks, activation flows, reports, and migrations against that role in a staging environment before changing Render's database connection.
4. Add precise RLS policies only for any data that genuinely must be queried directly by browser clients. Keep privileged identity tables inaccessible to `anon` and `authenticated`.
5. Enable leaked-password protection and review MFA/session settings for Vortex platform operators.
6. Re-run Supabase Security Advisor and the full application test suite after each change.

## Current boundary

The Vortex role separation in the application is implemented in FastAPI and the Vortex portal, but the role migration and owner bootstrap are not applied to the live project in this code change. The database connection role has not been changed. Do not treat this snapshot as a production-hardening sign-off.
