# School finance read RLS rehearsal

Scope: test-only candidate policies and controlled API integration. No production policy, grant, role, route dependency or migration is changed. These are not approved release migrations.

`scripts/rehearse_finance_api_rls.py` runs after the isolated financial migration rehearsal. It requires the existing loopback target guard plus `CHIKORO_REHEARSAL_FINANCE_API=yes`, rejects existing profiles/users, and uses synthetic financial fixtures. All new profiles, users, financial mutations, policies and role creation are enclosed in an outer transaction and rolled back. Cleanup is verified.

The test app includes the real `/payments` and `/invoices` routers. Only the database/principal dependencies are replaced to use TenantContextSession, the new identity wrapper and the isolated test connection. The real live-profile resolver, finance route authorization, serializers and balance calculations execute against PostgreSQL under a non-owner, non-superuser, non-BYPASSRLS role. JWT verification is mocked at the established verifier boundary; this is not a real Supabase login test.

## Candidate policy and grant slice

Ordinary finance reads require a verified subject, local-user context, matching school, profile role owner/headmaster/bursar, ordinary request kind and no platform-admin bypass.

| Table | Grant | Additional relationship boundary |
|---|---|---|
| students | SELECT id, school_id only | Own school; no activation/contact fields granted |
| invoices | SELECT | Referenced student must belong to the same school |
| payments | SELECT | Referenced student must belong to the same school |
| invoice_lines | SELECT | Referenced invoice must be visible and have the same school |
| payment_allocations | SELECT | Payment and invoice must both be visible, share school, learner and currency |
| receipts | SELECT | Referenced payment must be visible and have the same school |

Own-profile and linked-own-user SELECT policies/grants support identity bootstrap only; no staff-directory access or identity writes are granted. No financial writes, sequence privileges, special callback access or platform-wide school access are granted.

## Assertions

- School one owner, headmaster and bursar see only school one invoices/payments; school two owner sees only school two.
- Intentionally unscoped direct SQL still returns only valid own-school records in all six tables.
- Deliberately cross-linked student, invoice-line and receipt fixtures are hidden. A same-school allocation between different learners is hidden even though the current financial proposal does not constrain that equality for new writes.
- Real list/detail API routes return correct balances (70 and 80 in school one, 180 in school two) and invoice lines. Cross-school detail IDs and invalid-linked invoice IDs return 404; conflicting school query parameters return 403.
- Teacher, student, parent and tenant-free platform identities cannot use these school finance endpoints or read the six tables under this candidate finance policy slice. Their separate portal/academic/platform policies remain future work.
- Missing bearer credentials return 401. Forged role/school user metadata cannot override resolved profile data. Financial writes are rejected by database grants.

## Remaining gates

Review and finalize the table/column/route matrix, candidate predicates, index needs and representative data coverage before packaging migrations. Financial writes, voids, audit insertions, school locking and sequence privileges require a separate policy slice. Parent/student finance views, teacher/class policies, activation, Paynow callbacks and reconciliation are not implemented by these policies.

Run restricted-role integration against isolated Supabase staging with real Auth and representative data. Complete Storage/Auth integration, migration dependency and rollback validation, security settings and end-to-end role testing before production rollout. The production runtime continues to use its existing Session factory and connection.
