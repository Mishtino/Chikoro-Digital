# API and Edge Security Hardening

## Implemented in the application

The API now adds baseline response headers to every response:

- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy: camera=(), microphone=(), geolocation=()
- Cache-Control: no-store
- Strict-Transport-Security: max-age=31536000; includeSubDomains only when ENV=production.

These are defense-in-depth response controls. They do not constitute a WAF, network firewall, bot defense, or rate limiter. CORS is also not a firewall.

## Required before production release

1. Managed edge WAF and DDoS protection: choose and configure an explicitly supported provider in front of the public web/API origins. Enable managed OWASP protections, bot controls where appropriate, request-size limits, and monitored rate-based rules. Verify origin bypass is prevented or explicitly documented. Do not change DNS, nameservers, proxy mode, or production routing until the domain owner approves the provider and cutover plan.
2. Distributed API rate limiting: implement a shared Redis/managed-KV-backed limiter (not process-local memory) for login, bootstrap/activation, payment initiation, reconciliation, messaging, and expensive read/write endpoints. Define per-IP and per-account limits, trusted-proxy handling, 429 responses with Retry-After, atomic counters, TTLs, and a deliberate Redis outage policy. Never trust arbitrary X-Forwarded-For values; only parse forwarding headers from explicitly trusted proxy hops.
3. Origin and proxy trust: document the actual Render/Vercel proxy chain, client-IP header, trusted hosts, and direct-origin exposure. Validate host/origin assumptions before relying on edge rules.
4. Security headers: keep the API header tests. Separately define and test a CSP for each Next.js portal based on its actual scripts, styles, fonts, Supabase connections, and payment flows; do not copy an API CSP onto the browser portals blindly.
5. Observability: log rate-limit decisions and edge WAF events without logging credentials, tokens, PINs, payment secrets, or sensitive learner data. Alert on sustained 401/403/429 spikes, WAF blocks, and upstream availability failures.
6. Verification: exercise allowed and blocked traffic in staging, including login brute-force simulations, burst traffic, spoofed forwarding headers, oversized bodies, cross-tenant requests, payment callback behavior, and Redis outage behavior. Record provider configuration, rule IDs, thresholds, and rollback steps.

## Release status

- Baseline API response headers: implemented in application code; automated tests added.
- Distributed rate limiting: not yet implemented; release blocker.
- Managed WAF/DDoS: not yet selected or configured; release blocker.
- Portal CSP: pending portal-specific review and tests.
- Staging validation and production cutover: pending.

Do not claim Chikoro Digital is protected by an active WAF until a provider is configured, DNS/origin routing is verified, and test traffic confirms the rules are enforced. Do not deploy production changes or weaken existing origin controls as part of this work without an approved cutover plan.
