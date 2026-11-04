-- Chikoro Digital / Vortex platform
-- READ-ONLY production/staging preflight. Run with a role allowed to inspect
-- catalog metadata and the application tables. This file contains SELECTs only.
-- Do not append DDL or write statements to this audit.

-- 1) Compare the remote Supabase migration ledger with repository migrations.
SELECT version, name
FROM supabase_migrations.schema_migrations
ORDER BY version;

-- 2) RLS, FORCE RLS, and policy count for public tables.
SELECT
    c.relname AS table_name,
    c.relrowsecurity AS rls_enabled,
    c.relforcerowsecurity AS force_rls,
    COUNT(p.policyname)::integer AS policy_count
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
LEFT JOIN pg_policies AS p
    ON p.schemaname = n.nspname
   AND p.tablename = c.relname
WHERE n.nspname = 'public'
  AND c.relkind = 'r'
GROUP BY c.relname, c.relrowsecurity, c.relforcerowsecurity
ORDER BY c.relname;

-- 3) Browser-role table grants. Expected application data access is via API,
-- not direct anon/authenticated table access, except explicitly approved paths.
SELECT grantee, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
  AND grantee IN ('anon', 'authenticated')
ORDER BY grantee, table_name, privilege_type;

-- 4) Profiles structure, constraints, and role distribution.
SELECT
    column_name, data_type, character_maximum_length,
    is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'profiles'
ORDER BY ordinal_position;

SELECT conname, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.profiles'::regclass
ORDER BY conname;

SELECT role, COUNT(*)::bigint AS profile_count,
       COUNT(*) FILTER (WHERE school_id IS NULL)::bigint AS unscoped_count
FROM public.profiles
GROUP BY role
ORDER BY role;

-- 5) Identity bridge integrity. Counts only; do not return user emails or IDs.
SELECT
    COUNT(*)::bigint AS total_profiles,
    COUNT(*) FILTER (WHERE p.local_user_id IS NOT NULL)::bigint AS linked_profiles,
    COUNT(*) FILTER (WHERE p.local_user_id IS NULL)::bigint AS unlinked_profiles,
    COUNT(*) FILTER (WHERE p.local_user_id IS NOT NULL AND u.id IS NULL)::bigint AS orphaned_local_links,
    COUNT(*) FILTER (WHERE au.id IS NULL)::bigint AS missing_auth_users
FROM public.profiles AS p
LEFT JOIN public.users AS u ON u.id = p.local_user_id
LEFT JOIN auth.users AS au ON au.id = p.id;

SELECT
    COUNT(*)::bigint AS confirmed_auth_matches_for_active_unscoped_admins
FROM public.users AS u
JOIN auth.users AS au ON lower(au.email) = lower(u.email)
WHERE u.is_admin = true
  AND u.role = 'admin'
  AND u.is_active = true
  AND u.school_id IS NULL
  AND au.email_confirmed_at IS NOT NULL;

-- 6) Financial table row counts.
SELECT 'payments' AS table_name, COUNT(*)::bigint AS row_count FROM public.payments
UNION ALL SELECT 'payment_allocations', COUNT(*)::bigint FROM public.payment_allocations
UNION ALL SELECT 'receipts', COUNT(*)::bigint FROM public.receipts
UNION ALL SELECT 'invoices', COUNT(*)::bigint FROM public.invoices
UNION ALL SELECT 'paynow_attempts', COUNT(*)::bigint FROM public.paynow_attempts;

-- 7) Financial duplicate and tenant-integrity anomalies. Each result should be 0.
SELECT 'duplicate_paynow_payment_references' AS check_name, COUNT(*)::bigint AS issue_groups
FROM (
    SELECT reference
    FROM public.payments
    WHERE reference LIKE 'paynow:%'
    GROUP BY reference
    HAVING COUNT(*) > 1
) AS d
UNION ALL
SELECT 'duplicate_payment_invoice_allocation_pairs', COUNT(*)::bigint
FROM (
    SELECT payment_id, invoice_id
    FROM public.payment_allocations
    GROUP BY payment_id, invoice_id
    HAVING COUNT(*) > 1
) AS d
UNION ALL
SELECT 'duplicate_school_receipt_numbers', COUNT(*)::bigint
FROM (
    SELECT school_id, receipt_number
    FROM public.receipts
    GROUP BY school_id, receipt_number
    HAVING COUNT(*) > 1
) AS d
UNION ALL
SELECT 'cross_school_allocations', COUNT(*)::bigint
FROM public.payment_allocations AS pa
JOIN public.payments AS p ON p.id = pa.payment_id
JOIN public.invoices AS i ON i.id = pa.invoice_id
WHERE pa.school_id <> p.school_id
   OR pa.school_id <> i.school_id
   OR p.school_id <> i.school_id
UNION ALL
SELECT 'cross_student_allocations', COUNT(*)::bigint
FROM public.payment_allocations AS pa
JOIN public.payments AS p ON p.id = pa.payment_id
JOIN public.invoices AS i ON i.id = pa.invoice_id
WHERE p.student_id <> i.student_id;

-- 8) Database-level uniqueness backstops.
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('payments', 'payment_allocations', 'receipts')
ORDER BY tablename, indexname;

-- 9) Relevant database role capabilities. This does not identify which role
-- the deployed Render API connection actually uses.
SELECT rolname, rolsuper, rolbypassrls, rolcanlogin
FROM pg_roles
WHERE rolname IN ('postgres', 'service_role', 'authenticated', 'anon', 'authenticator')
ORDER BY rolname;
