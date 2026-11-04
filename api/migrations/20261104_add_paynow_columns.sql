-- Additive schema repair for the existing Chikoro Supabase database.
-- Safe to re-run: every column and index uses IF NOT EXISTS.
-- Existing school/payment rows are preserved.
ALTER TABLE public.schools
    ADD COLUMN IF NOT EXISTS paynow_integration_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS paynow_integration_key VARCHAR(500),
    ADD COLUMN IF NOT EXISTS paynow_test_mode BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE public.paynow_attempts
    ADD COLUMN IF NOT EXISTS reference VARCHAR(120),
    ADD COLUMN IF NOT EXISTS browser_url TEXT;

CREATE INDEX IF NOT EXISTS ix_paynow_attempts_reference
    ON public.paynow_attempts (reference);
