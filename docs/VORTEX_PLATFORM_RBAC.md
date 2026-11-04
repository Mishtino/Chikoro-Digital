# Vortex platform role-based access control

Chikoro Digital separates Vortex platform operations from school administration.
A Vortex role is a platform-level identity with no school tenant. School roles
remain tenant-scoped and cannot acquire platform permissions through profile
metadata or a school administrator role.

## Platform roles

| Role | Intended access |
| --- | --- |
| `vortex_admin` | Platform owner; school directory, school creation/lifecycle, audit feed, staff invitations and access identity |
| `vortex_support` | Read-only school directory and individual school records |
| `vortex_auditor` | Read-only platform audit feed |
| `vortex_billing` | Reserved for billing read access; billing screens/API are not yet enabled |

The API permission policy is centralized in
`api/app/services/platform_access.py`. The owner-only `platform:staff:write` permission controls staff governance. The dashboard uses the server-returned
permission list to hide unavailable controls. The API independently enforces
permissions; hiding a button is not treated as a security boundary.

## Identity requirements

A platform profile must:
- have a matching, active local `public.users` record;
- have `school_id IS NULL` in both the local user and trusted profile;
- use the same role in both records;
- use `is_admin = true` only for the dedicated `vortex_admin` owner;
- be linked to a verified Supabase Auth identity.

Authorization never trusts user-editable Supabase `user_metadata`.

## Migration and provisioning status

Migration `202611040003_vortex_staff_roles.sql` expands the trusted profile role
allow-list. It is committed but **has not been applied** to the live database.

Owner-only Vortex staff invitations are implemented at
`POST /platform/staff/invitations`; `GET /platform/staff` lists linked
platform identities. Only the `vortex_admin` owner can use either endpoint.
Invitations can assign `vortex_support` or `vortex_auditor`; the owner role
can only be established through the guarded bootstrap. Billing remains
reserved until its module is available.

The API uses `SUPABASE_SECRET_KEY` only on the trusted Render server. Never
add it to Vercel, a browser bundle, or any `NEXT_PUBLIC_*` variable. Supabase
Auth creates and emails the invitation first; the API then writes the local
user, trusted profile bridge and audit event in one database transaction. If
linking fails, it attempts to delete the Auth user so the invitation is
invalidated. The endpoint fails closed until the trusted profile role
constraint contains both supported staff roles.

The invitation workflow is not production-ready until migrations
`202611040002_vortex_platform_role.sql` and
`202611040003_vortex_staff_roles.sql` are reviewed and applied, the Render
secret is configured, and the Supabase Auth invite email/redirect configuration
is verified. Until then, keep the existing Vortex owner as the only provisioned
platform account. Do not manually promote a school account, set `is_admin`, or
create profile rows from a browser/client.
