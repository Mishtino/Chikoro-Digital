-- Supabase identity bridge. Apply through a reviewed Supabase migration.
-- This table is intentionally inaccessible to browser roles: FastAPI resolves
-- identities through its server-side database connection.
BEGIN;

CREATE TABLE IF NOT EXISTS public.profiles (
    id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    local_user_id integer UNIQUE REFERENCES public.users(id) ON DELETE RESTRICT,
    role varchar(50) NOT NULL,
    school_id integer REFERENCES public.schools(id) ON DELETE RESTRICT,
    is_active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT profiles_role_check CHECK (
        role IN ('student','parent','teacher','bursar','headmaster','owner','admin','vortex_admin','pending')
    )
);

CREATE INDEX IF NOT EXISTS ix_profiles_school_id ON public.profiles(school_id);
CREATE INDEX IF NOT EXISTS ix_profiles_local_user_id ON public.profiles(local_user_id);

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles FORCE ROW LEVEL SECURITY;

-- No browser-side SELECT/INSERT/UPDATE/DELETE. Authenticated clients use
-- Supabase Auth; privileged identity linking is performed by trusted backend
-- provisioning only. Never grant service_role or secret keys to a client.
REVOKE ALL ON TABLE public.profiles FROM anon, authenticated;

COMMIT;
