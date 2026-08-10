# Operations and observability

## Runtime contract

- Service: `ai-cv-advisory-board-production`
- Google Cloud project: `ai-cv-advisory-board`
- Region: `us-central1`
- Runtime: stateless Cloud Run container, scale-to-zero allowed
- Health contract: `GET /api/health` returns `{"status":"ok"}`
- Firestore: owner-scoped applications, CV metadata/extracted text, and monthly AI ledgers
- Cloud Storage: private immutable CV bytes in `users/{subject}/cv-versions/...`
- Vertex AI model: `gemini-2.5-flash`, global endpoint, thinking disabled
- Identity: Google ID token; stable `sub` claim is the owner key
- AI ceilings: $5/month shared anonymous, $10/month per approved user, and $50/month project-wide
- Burst guards: 2 anonymous AI attempts/minute/client and 10 approved attempts/minute/user

Production environment variables:

- `ADVISORY_ENVIRONMENT=production`
- `ADVISORY_REPOSITORY_BACKEND=firestore`
- `ADVISORY_AUTH_MODE=google`
- `ADVISORY_GOOGLE_OAUTH_CLIENT_ID=<web client ID>`
- `ADVISORY_CV_BUCKET=ai-cv-advisory-board-production-cvs`

## Structured events

The `advisory` logger emits one-line JSON events:

| Event | Safe fields | Use |
|---|---|---|
| `cv.ingestion.completed` | source, file_bytes, cv_chars | Upload/paste volume and parser success |
| `cv.ingestion.failed` | source, file_bytes, error_type | File recovery rate |
| `job.ingestion.completed` | source, job_chars | URL versus paste usage |
| `job.ingestion.failed` | source, error_type | Remote-page recovery rate |
| `operation.started/finished/failed` | operation, run_id, duration_ms, error_type | Assessment latency and failures |
| `assessment.completed` | run_id, lengths, score, scoring_version | Scoring throughput and version audit |
| `application.created/updated` | opaque user/application IDs, status | Pipeline activity |
| `cv_version.created` | opaque user/version IDs, byte count | Immutable CV creation |
| `gemini.request.completed` | opaque user ID, model, tokens, micro-USD, duration | AI cost and latency |
| `gemini.request.failed` | opaque user ID, model | Provider failure rate |
| `security.access_denied` | route, method, 401/403 status | Authentication/authorization abuse |
| `security.cross_site_blocked` | route, method, fetch metadata | Cross-site mutation attempts |
| `security.ai_burst_blocked` | access tier | AI burst guard activations |
| `workspace.archived/archive_viewed` | opaque owner/archive IDs and record counts | Read-only workspace-history lifecycle |

The logging safety filter removes document text, filenames, credentials, prompts, and full URLs even when
those fields are passed accidentally.

## Signals to watch

- Health availability and non-2xx rate.
- p50/p95 assessment latency from `operation.finished`.
- Ratio of `job.ingestion.failed` to URL-sourced completions; a rise usually means a job board changed or
  started blocking server-side reads.
- Ratio of upload failures to completions; a rise can indicate unsupported or scanned CV formats.
- Cloud Run instance count, request concurrency, outbound latency, and billable instance time.
- AI used plus reserved micro-USD; the transaction must never allow their sum above the user limit.
- Stale reservation documents, which indicate an interrupted model request and require reconciliation.

No alert threshold is encoded yet because the service has one private user and no traffic baseline. Establish
a seven-day baseline before choosing thresholds; until then, any sustained health failure or repeated server
error is actionable.

## Deployment verification

1. Run Ruff, mypy, unit/integration tests with coverage, offline evaluations, and all Playwright tests.
2. Build and deploy from the personal repository to the named project and service.
3. Confirm the new revision receives 100% of traffic and `/api/health` succeeds.
4. In a real browser, verify Google sign-in, application creation, status movement, funnel updates, immutable CV
   attachment, AI budget display, the retained evidence-review flow, mobile overflow, and a clean console.
5. If verification fails, route traffic back to the prior healthy revision and investigate without deleting it.

## Failure recovery

- Job page blocked or unreadable: preserve the parsed CV and use the manual description fallback.
- Scanned/image-only PDF: use an exported text PDF, TXT file, or paste the text.
- Health failure after rollout: restore the prior Cloud Run revision's traffic, then inspect application logs.
- Unexpected content in logs: stop traffic, preserve metadata-only diagnostic evidence, and treat it as a
  privacy incident.
