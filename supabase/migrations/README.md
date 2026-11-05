# Supabase migration directory — temporarily blocked

**Do not run `supabase db push` or apply migrations from this repository until this notice is removed.**

The connected production project has four applied migration versions whose original SQL files are not present in this repository. The three previously tracked local migration drafts did not match the live migration ledger or live schema and have been moved to `supabase/proposed_migrations/` so they cannot be picked up by the normal Supabase migration command.

The exact original SQL must be recovered and migration history reconciled before this directory is repopulated with the canonical migration chain.

Current forward-only role-allow-list draft:
`supabase/proposed_migrations/20261105_add_profiles_platform_role_allowlist.sql`

That file is staging-only and is not approved for production application. It preserves the live foreign keys, RLS settings, grants, and profile-read policy. See `docs/SUPABASE_MIGRATION_RECONCILIATION.md`.

No migration has been applied by this repository change.
