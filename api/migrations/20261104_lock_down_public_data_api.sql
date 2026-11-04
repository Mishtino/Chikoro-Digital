-- Emergency fail-closed lockdown for the Supabase Data API.
-- All application business operations continue through the trusted FastAPI
-- database connection. Client-side table access remains disabled until each
-- table has an explicit, tested role/tenant policy.
do $$
declare t record;
begin
  for t in
    select c.relname
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relkind in ('r','p')
  loop
    execute format('alter table public.%I enable row level security', t.relname);
    execute format('revoke all privileges on table public.%I from anon, authenticated', t.relname);
  end loop;
end
$$;

do $$
declare s record;
begin
  for s in
    select c.relname
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relkind = 'S'
  loop
    execute format('revoke all privileges on sequence public.%I from anon, authenticated', s.relname);
  end loop;
end
$$;

-- Supabase Auth users may read only their own identity/profile row.
grant select on table public.profiles to authenticated;
