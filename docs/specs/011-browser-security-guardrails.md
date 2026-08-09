# Spec 011: Browser security guardrails

## Objective

Protect authenticated career data and AI actions at the HTTP boundary without weakening the public, no-login workflow or relying only on client-side behavior.

## Controls

- Unsafe cross-site browser requests are rejected using Fetch Metadata and strict Origin comparison.
- Production accepts writes only from the configured canonical application origin.
- The Google session credential is stored in a host-only, `Secure`, `HttpOnly`, `SameSite=Lax` cookie scoped to `/` and limited to one hour.
- Logout expires the cookie with matching security attributes.
- Private API responses use `Cache-Control: no-store`.
- Every response receives a restrictive Content Security Policy, clickjacking protection, MIME-sniffing protection, a limited referrer policy, and a permissions policy that disables camera, microphone, geolocation, and payment access.
- Production responses enable one-year HSTS.
- The CSP permits only first-party assets plus the minimum Google Identity Services origins required for sign-in. Object embedding and third-party framing are denied.

## Acceptance criteria

- Cross-site POST, PATCH, PUT, and DELETE attempts return HTTP 403 before business logic runs.
- Same-origin writes and non-browser test/service clients continue to work.
- Google sign-in remains functional under CSP.
- Authenticated API responses are not browser-cacheable.
- Security headers are covered by automated regression tests and verified again on the deployed Cloud Run revision.
