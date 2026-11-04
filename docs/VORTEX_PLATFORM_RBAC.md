# Vortex platform role-based access control

Chikoro Digital separates Vortex platform operations from school administration.
A Vortex role is a platform-level identity with no school tenant. School roles
remain tenant-scoped and cannot acquire platform permissions through profile
metadata or a school administrator role.

## Platform roles

| Role | Intended access |
| --- | --- |
| `vortex_admin` | Platform owner; school directory, school creation/lifecycle, audit feed, access identity |
| `vortex_support` | Read-only school directory and individual school records |
| `vortex_auditor` | Read-only platform audit feed |
| `vortex_billing` | Reserved for billing read access; billing screens/API are not yet enabled |

The API permission policy is centralized in
`api/app/services/platform_access.py`. The dashboard uses the server-returned
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

Additional Vortex staff invitation/provisioning is intentionally not exposed yet.
There is no public endpoint for creating platform staff, and the legacy
`POST /users` local-password provisioning endpoint remains disabled. Do not
manually promote a school account, set `is_admin`, or create profile rows from
a browser/client. A future owner-only invitation workflow must use a
server-side Supabase Auth Admin credential, verify the invite/identity link,
write both identity records atomically with compensation on failure, and audit
the action. The service-role key must never enter a browser bundle or
`NEXT_PUBLIC_*` variable.

Until that workflow is delivered and the migration is reviewed/applied, keep
the existing Vortex owner as the only provisioned platform account.
