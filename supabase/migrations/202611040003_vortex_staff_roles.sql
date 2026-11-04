-- Allow explicitly provisioned Vortex platform staff roles.
-- This changes the trusted profile role allow-list only; it does not create,
-- invite, activate, or promote any account.
BEGIN;

ALTER TABLE public.profiles
    DROP CONSTRAINT IF EXISTS profiles_role_check;

ALTER TABLE public.profiles
    ADD CONSTRAINT profiles_role_check CHECK (
        role IN (
            'student', 'parent', 'teacher', 'bursar', 'headmaster', 'owner',
            'admin', 'vortex_admin', 'vortex_support', 'vortex_auditor',
            'vortex_billing', 'pending'
        )
    );

COMMIT;
