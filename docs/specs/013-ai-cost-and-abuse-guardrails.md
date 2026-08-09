# 013 — AI cost and abuse guardrails

## Decision

Upgrade production reviews to the GA `gemini-2.5-flash` model while bounding financial exposure at three independent scopes:

1. Every anonymous user shares a USD 5 calendar-month AI pool.
2. Every approved Google identity receives a USD 10 calendar-month AI allowance.
3. All model traffic shares a USD 50 calendar-month emergency ceiling.

The application reserves the maximum configured request cost against both the tier ledger and the project ledger before contacting Vertex AI. It reconciles both reservations to provider-reported token usage after success and releases both after provider failure.

## Abuse controls

- Anonymous AI: at most two attempts per rolling minute and client fingerprint.
- Approved AI: at most ten attempts per rolling minute and verified Google subject.
- Cloud Run: at most two active instances.
- Uploads remain bounded to 5 MiB and extracted content to the configured character limit.
- Cross-site mutations are rejected before route execution.

The rolling-minute limiter is deliberately a low-cost, per-instance burst brake. The Firestore reservation ledgers are the durable and horizontally consistent financial authority.

## Alert contract

Cloud Logging receives structured events without CV text, job text, filenames, URLs, tokens, or email addresses:

- `security.access_denied` for 401 and 403 responses.
- `security.cross_site_blocked` for rejected cross-site mutations.
- `security.ai_burst_blocked` when a tier exceeds its burst allowance.
- `cv_version.created` for bounded upload-volume monitoring.
- `gemini.request.completed` and `gemini.cv_review.completed` for AI volume and estimated cost.

Cloud Monitoring alert policies notify `carlosan.1708@gmail.com` when security denials, uploads, or AI activity cross their operational thresholds. The email notification channel must be verified by its recipient before Google can deliver incidents.

## Acceptance criteria

- No Gemini call begins unless both applicable ledgers accept the maximum-cost reservation.
- A failed second reservation releases the first reservation.
- A successful call charges both ledgers the same actual token-derived cost.
- Approved-user budget API returns limit, used, reserved, and remaining micro-USD.
- Exhausted budgets and burst limits return HTTP 429 for private APIs.
- Anonymous deterministic analysis remains usable when free AI is exhausted or rate-limited.
- Security telemetry contains no document contents or direct user identifiers beyond the existing opaque Google subject.
- Unit, API, static analysis, Playwright, and live browser regression checks pass before traffic promotion.
