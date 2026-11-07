# Paynow integration security review

**Reviewed:** 5 November 2026  
**Status:** code hardening prepared on the feature branch; live payment verification still required before release.

## Official provider behavior verified

The current Paynow Zimbabwe Developer Hub states:

- Initiation uses HTTPS at `https://www.paynow.co.zw/interface/initiatetransaction`.
- A successful initiation response includes `BrowserUrl`, `PollUrl`, status and hash.
- The merchant must verify the initiation response hash before redirecting the customer to `BrowserUrl`.
- Polling uses an empty HTTP POST to the provider-returned `PollUrl`, not GET.
- Status updates are sent to the merchant result URL; the merchant must validate their hash and is advised to poll Paynow to confirm important updates.

Official documentation:
- [Initiate a transaction](https://developers.paynow.co.zw/docs/paynow/initiate_transaction/)
- [Polling for a Status Update](https://developers.paynow.co.zw/docs/paynow/polling_status/)
- [Status Update](https://developers.paynow.co.zw/docs/paynow/status_update/)

## Changes prepared on the feature branch

- Poll requests use an empty POST.
- HTTP redirects are disabled for poll requests.
- Provider-returned checkout and polling URLs must use HTTPS and the exact documented host `www.paynow.co.zw`, with the default HTTPS port only.
- Initiation responses must pass hash verification before checkout/poll URLs are persisted or returned to a browser.
- The response parser accepts Paynow's documented capitalized fields (for example `Status`, `BrowserUrl`, `PollUrl`, `Hash`) as well as lowercase variants.
- Tests cover POST usage, disabled redirects, unverified initiation signatures, and rejection of lookalike/noncanonical hosts.

## Compatibility item to confirm with Paynow

The current Developer Hub's success-response example still displays legacy `http://www.paynow.co.zw:7106` BrowserUrl and PollUrl values, while its current initiation endpoint and polling response examples use HTTPS on `www.paynow.co.zw`. Chikoro intentionally rejects HTTP and non-standard ports rather than silently weakening transport security.

Before enabling Paynow for production schools, complete a real test-mode checkout and confirm the actual BrowserUrl and PollUrl returned for the merchant integration use HTTPS on `www.paynow.co.zw`. If the provider still returns the legacy HTTP/7106 URLs, obtain written provider confirmation of a supported secure endpoint. Do not add broad host wildcards, follow redirects, or allow arbitrary ports as a workaround.

## Release checks

- [ ] Test initiation response hash verification with a genuine Paynow test transaction.
- [ ] Confirm checkout and poll URL host/scheme/port from the actual provider response.
- [ ] Confirm polling by empty POST returns a signed status response.
- [ ] Confirm webhook hash validation and subsequent poll confirmation.
- [ ] Verify cancelled, disputed, refunded, duplicate, late and out-of-order callbacks do not create or reverse incorrect financial records.
- [ ] Verify provider outage/timeouts leave the attempt retryable and do not mark an unpaid invoice as paid.
- [ ] Only then include Paynow API code in the coordinated production release.


## Additional callback/reconciliation hardening

A source review found that the webhook and reconciliation paths previously trusted an unsigned callback status as a fallback when the provider poll did not return a status, and reconciliation could accept unsigned Cancelled/Failed results. This could let an unauthenticated callback disrupt a checkout's local status even though it could not create a verified payment.

The API change now:
- Treats callback form data only as a wake-up signal and never as the source of payment status.
- Requires every state-changing status to come from a provider poll response with a valid hash and the exact merchant reference for that attempt.
- Requires the exact amount as well as hash/reference for Paid.
- Does not overwrite the provider reference from unverified callback fields.
- Marks unverified provider results for reconciliation rather than accepting unsigned cancellation/failure states.
- Accepts Cancelled/Failed/Disputed only when the provider poll response is signed and bound to the attempt.

Regression tests cover forged cancellation callbacks, unsigned reconciliation failure, signed pending/cancelled responses and the existing paid-settlement/idempotency flows.

