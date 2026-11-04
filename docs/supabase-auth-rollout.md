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
- The student activation path uses a verified Supabase Auth identity plus a school-issued one-time PIN. Parent activation is not yet exposed in the portal.
- Parent activation is implemented as a separate verified-contact flow. School owners/headmasters issue a one-time 24-hour PIN for a recorded guardian contact; the guardian must create a Supabase Auth identity, confirm their email, and present the school code, contact ID and PIN. FastAPI checks that the confirmed Auth email exactly matches the school's contact email, consumes the PIN once, and creates an active `guardian_links` mapping. A parent can link multiple contacts within the same school. Never link by student number or browser-supplied relationship alone.
- Student enrollment responses now include the guardian contact ID when a guardian contact is recorded. Staff and Vortex administrator invitations still require a controlled provisioning workflow; do not enable public signup as a route to privileged roles.
- The live Render service now has `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` configured. The latest configuration-triggered deployment was reported live; this does not mean any Auth account has been provisioned.
- A production Data API lockdown migration has been applied: RLS is enabled on every public table; `anon` has no table/sequence privileges; `authenticated` has only SELECT on `profiles`, governed by the own-profile policy. Direct client queries and realtime subscriptions to other public tables will remain unavailable until explicit policies and grants are added.
- Backend API access is intended to continue through the trusted Render database connection. Before further table-policy rollout, verify that this connection uses a trusted owner/BYPASSRLS-capable role; never expose that credential to a browser.
- Financial tables, Paynow credentials, audit logs, notification queues and student records must stay backend-only until narrowly scoped policies are implemented and tested.
- The existing administrator is still not linked: the production database audit found one local user and zero Supabase Auth users. Do not cut over administrator login until the real owner has created/confirmed their Auth identity and the exact UUID has been linked by an authorized operator.
