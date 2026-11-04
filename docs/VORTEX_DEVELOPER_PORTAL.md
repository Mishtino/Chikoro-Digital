# Vortex Technologies Developer Portal

The Vortex portal is the platform-operator workspace for Chikoro Digital. It is separate from school administration accounts.

## Role boundary

- Vortex platform owner: Supabase profile role `vortex_admin`, linked to an active local `users` record with `is_admin = true` and `school_id IS NULL`.
- School administrators and staff: school-scoped roles linked to their own school. They do not receive the Vortex portal role or global platform access.
- Browser clients never decide their own role. FastAPI resolves the Supabase Auth UUID through `public.profiles` and checks the linked local user record.

## First-time owner provisioning

1. Create and verify the owner's Supabase Auth identity using the exact address reserved for the Vortex platform owner.
2. Ensure the matching local `public.users` record exists, is active, has `role = 'admin'`, `is_admin = true`, and `school_id IS NULL`. Do not attach this identity to a school.
3. Set `VORTEX_PLATFORM_OWNER_EMAIL` to that exact verified address in the Render API environment.
4. Set a one-time `ADMIN_BOOTSTRAP_TOKEN` of at least 32 characters in the same environment. Keep it secret; never put it in a browser variable or source control.
5. Apply the reviewed Supabase migrations in order. The Vortex role migration only promotes matching platform-owner profiles; it does not change school accounts.
6. Call `POST /auth/bootstrap-admin` once with the bootstrap token in the `X-Chikoro-Bootstrap-Token` header. The endpoint requires an empty profiles table and a unique, confirmed Supabase identity matching the configured owner email.
7. Remove or rotate the bootstrap token after successful provisioning. Sign in through the Vortex portal and verify `GET /auth/supabase/me` returns `is_platform_admin: true`.

## Security notes

- Do not create the platform owner through public registration.
- Do not use the developer's email as a school administrator account.
- The portal checks `is_platform_admin`; FastAPI independently enforces the role on platform-wide school management endpoints.
- The service database connection and RLS policies must be reviewed before production rollout. Never expose the Supabase service-role key to browser code.
- Applying migrations and setting Render environment variables are deployment operations and must be performed separately from merging these repository changes.
