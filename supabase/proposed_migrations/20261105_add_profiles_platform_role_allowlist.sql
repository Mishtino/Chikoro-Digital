-- PROPOSED FOR STAGING ONLY — NOT PART OF THE AUTOMATIC SUPABASE MIGRATION SET.
--
-- Live production schema was inspected read-only on 2026-11-05.
-- The live profiles table has no role CHECK constraint, uses ON DELETE SET NULL
-- on local_user_id/school_id, and has an authenticated own-profile SELECT policy.
-- This forward-only change intentionally preserves all of those properties.
--
-- Do not apply until the original live migration SQL has been recovered,
-- migration history has been reconciled, and this file has passed on a staging
-- clone. Do not place this file in supabase/migrations until that is approved.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.profiles'::regclass
          AND conname = 'profiles_role_check'
    ) THEN
        RAISE EXCEPTION
            'profiles_role_check already exists; inspect its definition before applying this proposal';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public.profiles
        WHERE role NOT IN (
            'student', 'parent', 'teacher', 'bursar', 'headmaster', 'owner',
            'admin', 'vortex_admin', 'vortex_support', 'vortex_auditor',
            'vortex_billing', 'pending'
        )
    ) THEN
        RAISE EXCEPTION
            'profiles contains roles outside the approved Chikoro/Vortex allow-list';
    END IF;
END
$$;

ALTER TABLE public.profiles
    ADD CONSTRAINT profiles_role_check
    CHECK (
        role IN (
            'student', 'parent', 'teacher', 'bursar', 'headmaster', 'owner',
            'admin', 'vortex_admin', 'vortex_support', 'vortex_auditor',
            'vortex_billing', 'pending'
        )
    ) NOT VALID;

ALTER TABLE public.profiles
    VALIDATE CONSTRAINT profiles_role_check;

COMMIT;
