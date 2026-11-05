# Zero-cost local PostgreSQL validation

This local database is intended for development and migration rehearsal only. It is not a Supabase replacement and must never be used as a production database.

## Requirements

- Docker Engine or Docker Desktop with the Compose plugin.
- No paid cloud database or Supabase staging branch is required.

## Start the isolated database

From the repository root:

```bash
docker compose -f docker-compose.local.yml --profile local-db up -d
docker compose -f docker-compose.local.yml ps
```

Connection string for local-only tools:

```text
postgresql://chikoro_local:local_only_change_me@127.0.0.1:55432/chikoro_local
```

The port is bound to loopback only. The named volume persists between restarts. The credentials are deliberately fixed for convenience and are unsafe for any shared or internet-facing environment.

## Stop and reset

Stop the database but retain its data:

```bash
docker compose -f docker-compose.local.yml --profile local-db down
```

Destroy the local database and all data in its named volume (irreversible):

```bash
docker compose -f docker-compose.local.yml --profile local-db down -v
```

## Migration rehearsal rules

1. Confirm the active connection string points to `127.0.0.1:55432/chikoro_local` before running SQL.
2. Use synthetic school, learner, guardian and payment records only.
3. Apply proposed SQL files one at a time and record the exact command, result and rollback/recovery procedure.
4. Verify constraints, indexes, RLS enablement, policies and grants after each change.
5. Keep Supabase-specific migrations involving Auth, Storage, extensions or platform-managed objects marked as requiring Supabase staging validation. A plain PostgreSQL container cannot prove those integrations work.
6. Never copy production credentials or personal data into this database.
7. Never point migration tooling at the production project from this workflow.

## Current limitations

This Compose file only provisions PostgreSQL 17. It does not automatically apply any migration, seed data, change application configuration, or connect to Supabase. The existing SQLite quick-start remains available for lightweight API development. Use this PostgreSQL instance for database-specific rehearsal before any paid or production environment is considered.
