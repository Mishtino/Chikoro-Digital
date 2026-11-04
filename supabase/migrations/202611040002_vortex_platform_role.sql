-- Promote only existing Vortex platform operator profiles to the dedicated role.
-- School-scoped accounts are never changed by this migration.
BEGIN;

UPDATE public.profiles AS p
SET role = 'vortex_admin',
    updated_at = now()
FROM public.users AS u
WHERE u.id = p.local_user_id
  AND u.is_admin = true
  AND u.role = 'admin'
  AND u.school_id IS NULL
  AND p.school_id IS NULL
  AND p.role = 'admin';

COMMIT;
