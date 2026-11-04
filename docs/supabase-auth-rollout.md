# Supabase Auth rollout and account provisioning

## Architecture

- Supabase Auth is the sole production credential provider.
- Next.js clients use the Supabase publishable key only.
- FastAPI validates access tokens through the Supabase Auth `/auth/v1/user` endpoint.
- Authorization is loaded from `public.profiles`; role and school claims supplied by the browser are ignored.
- `public.users` remains the legacy application record during the migration. `profiles.local_user_id` maps the Supabase UUID to that row.

## Student self-activation

1. The learner creates a Supabase Auth identity using a verified email address.
2. The Auth trigger creates an inactive `pending` profile.
3. The learner confirms their email and signs in.
4. The learner submits their school code, student number and one-time activation PIN.
5. FastAPI verifies the Supabase access token, validates the school's activation PIN, creates the local user, and links the profile to the student.
6. The activation PIN is consumed and cannot be reused.

The API never accepts a local user ID, role or school assignment from the browser during this process.

## Existing staff and Vortex administrator migration

Existing accounts must be migrated by an authorized operator. Do not match and link accounts automatically by email.

For each account:

1. Verify the person's identity and ownership of the existing account out of band.
2. Create or invite their Supabase Auth identity using the Supabase Dashboard.
3. Require email confirmation and an initial password reset.
4. Confirm exactly one matching active row exists in `public.users`.
5. Execute the following transaction with the exact verified Supabase UUID and local integer user ID. Do not derive either identifier from untrusted browser input.

```sql
begin;

-- Replace both values only after verifying the account owner.
insert into public.profiles
  (id, local_user_id, role, school_id, is_active, updated_at)
select
  'REPLACE_WITH_VERIFIED_AUTH_UUID'::uuid,
  u.id,
  case when u.is_admin then 'admin' else u.role end,
  u.school_id,
  u.is_active,
  now()
from public.users u
where u.id = REPLACE_WITH_VERIFIED_LOCAL_USER_ID
  and u.is_active = true
on conflict (id) do update
set local_user_id = excluded.local_user_id,
    role = excluded.role,
    school_id = excluded.school_id,
    is_active = excluded.is_active,
    updated_at = now();

-- Verify exactly one profile is linked before committing.
select p.id, p.local_user_id, p.role, p.school_id, p.is_active
from public.profiles p
where p.id = 'REPLACE_WITH_VERIFIED_AUTH_UUID'::uuid;

commit;
```

Do not run the sample with placeholders unchanged. If the result is not exactly the intended account, roll back instead of committing.

## Current limitations and rollout gates

- The live project currently has one local user and zero Supabase Auth users. No existing account has yet been linked.
- The student/parent portal activation path is implemented for student PINs. Parent/guardian linking needs a separate verified-contact workflow; do not grant parent access based only on knowing a student number.
- Staff account invitations still require a controlled provisioning workflow.
- Production FastAPI protected routes require `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` to be set on Render.
- Do not deploy the API until those variables are configured and the existing administrator is linked.
- Do not enable blanket table access or revoke backend database privileges until the Render database connection role has been verified.
- Direct client access to academic and financial tables must remain blocked until table-specific RLS policies and cross-school tests are approved.
