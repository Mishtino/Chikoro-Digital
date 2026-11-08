# Manual finance write RLS rehearsal

Status: local CI candidates only. No production role, grant, policy, connection, migration or dependency change. Keep production release on hold pending the complete policy/release gates.

The guarded finance API rehearsal now optionally runs write checks when `CHIKORO_REHEARSAL_FINANCE_WRITES=yes`. It first proves the existing read-only role cannot write, then installs the candidate write slice inside its rollback-only local fixture transaction. The role remains non-owner, non-superuser and non-BYPASSRLS. The real payment routes, allocation/receipt services and audited commits execute with identity bootstrap and transaction-local context. JWT verification is mocked at the established boundary; live profile resolution remains real.

The payment routes now select only learner IDs for membership checks and school IDs for row locks, reducing the required column privileges without changing authorization or lock order. The restricted finance role is not granted learner activation fields or school Paynow credentials.

## Candidate privilege slice

- School/invoice row locks receive SELECT and the minimum UPDATE(id) privilege, with UPDATE policies whose WITH CHECK is false. The locks can execute, but actual school/invoice updates are denied.
- Manual payment INSERT is limited to own-school learners, a positive amount, normalized currency, a nonempty non-Paynow method/reference and the current actor. Already-voided insertion is denied. INSERT column grants exclude explicit primary keys.
- Allocation INSERT requires a visible nonvoid payment belonging to the current actor and a visible nonvoid invoice matching school, learner and currency. Receipt INSERT similarly binds to the actor's visible nonvoid payment.
- Only owners/headmasters can update the payment void fields. Amounts, references and tenant identifiers are not updateable. Bursars retain record-only access.
- Audit INSERT binds school, actor, payment entity and supported action to a visible payment; void audits require owner/headmaster. Only audit ID can be selected for ORM RETURNING, and audit UPDATE/DELETE are not granted.
- USAGE is granted only on the four payment/allocation/receipt/audit sequences used by these inserts. The synthetic fixture sequences are transactionally restarted rather than using setval; fixture rollback restores the rehearsal changes.

## Assertions

Owners, headmasters and bursars record payments with allocations, receipts and audit records. School two remains independent. Owners/headmasters void within their own school; bursar voids and cross-school voids are denied, and repeated voids retain the existing API rejection. Invoice balances change correctly on payment and return on void.

Cross-school/cross-learner selection, overpayment, blank method, provider-only method, duplicate reference and unsupported-role requests are rejected without leaving partial payment/allocation/receipt/audit rows. Raw SQL checks separately reject cross-school/mismatched-learner inserts, forged audit actor/school, forbidden provider method, amount changes, deletes, actual school/invoice updates and secret-field reads. Exactly four record events and three void events must carry the expected actor, school and payment IDs; existing allocation/receipt records remain after void and the balance service ignores voided payments.

## Remaining gates and limits

These candidates cover ordinary manual payment/void workflows only. They are not approved Supabase migrations or complete database financial-integrity enforcement. Aggregate over-allocation remains enforced by the reviewed API's locked workflow; RLS predicates do not independently prove balance arithmetic under arbitrary SQL. Already-voided reason edits, stronger append-only financial semantics, concurrent sessions/deadlocks and race conditions need explicit database design/review and dedicated tests before release.

Paynow callbacks/reconciliation, fees/invoice generation, parent/student portal, staff/class/platform workflows and exceptional activation require separate policy slices. Finalize the full CRUD/column matrix, indexes and migration dependencies; run real Auth and restricted-role integration in isolated Supabase staging; verify backups, rollback, security settings and end-to-end flows. Production continues using its existing connection and Session factory.
