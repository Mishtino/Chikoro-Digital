-- PROPOSED FOR STAGING ONLY — NOT PART OF THE AUTOMATIC SUPABASE MIGRATION SET.
--
-- Read-only production audit on 2026-11-05 found:
--   * zero duplicate non-NULL payment references
--   * zero duplicate (payment_id, invoice_id) allocation pairs
--   * zero duplicate (school_id, student_id, term_id) invoices
-- This migration adds database uniqueness backstops consistent with the
-- SQLAlchemy models. It does not alter or rewrite financial data.
--
-- Apply only to a staging clone after the original live migration history has
-- been recovered and the resulting constraints have been verified there.
-- ALTER TABLE ... UNIQUE takes locks while PostgreSQL builds its indexes;
-- review table size/traffic and use an approved concurrent-index rollout if
-- the production workload requires avoiding that lock.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.invoices'::regclass
          AND conname = 'uq_invoice_student_term_per_school'
    ) THEN
        RAISE EXCEPTION
            'uq_invoice_student_term_per_school already exists; inspect it before applying this proposal';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.payments'::regclass
          AND conname = 'uq_payment_reference_per_school'
    ) THEN
        RAISE EXCEPTION
            'uq_payment_reference_per_school already exists; inspect it before applying this proposal';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.payment_allocations'::regclass
          AND conname = 'uq_payment_allocation_per_invoice'
    ) THEN
        RAISE EXCEPTION
            'uq_payment_allocation_per_invoice already exists; inspect it before applying this proposal';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public.invoices
        WHERE term_id IS NOT NULL
        GROUP BY school_id, student_id, term_id
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Duplicate learner/term invoices exist within a school; resolve before applying this proposal';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public.payments
        WHERE reference IS NOT NULL
        GROUP BY school_id, reference
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Duplicate payment references exist within a school; resolve before applying this proposal';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public.payment_allocations
        GROUP BY payment_id, invoice_id
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Duplicate payment/invoice allocation pairs exist; resolve before applying this proposal';
    END IF;
END
$$;

ALTER TABLE public.invoices
    ADD CONSTRAINT uq_invoice_student_term_per_school
    UNIQUE (school_id, student_id, term_id);

ALTER TABLE public.payments
    ADD CONSTRAINT uq_payment_reference_per_school
    UNIQUE (school_id, reference);

ALTER TABLE public.payment_allocations
    ADD CONSTRAINT uq_payment_allocation_per_invoice
    UNIQUE (payment_id, invoice_id);

COMMIT;
