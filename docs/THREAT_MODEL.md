# Threat model

## Assets

- CV bytes, extracted text, contact information, and filenames.
- Job URLs, descriptions, and the candidate's job-search intentions.
- Integrity of findings and recommendations.
- Google identity, Firestore records, private Cloud Storage objects, and Vertex AI usage.

## Trust boundaries

Browser input, uploaded documents, remote job pages, redirects, and model output are untrusted.
Application logs and downloadable artifacts are separate disclosure surfaces.

## Current controls

### CV ingestion

- PDF and UTF-8 TXT are the only accepted formats.
- Reads stop after 5 MiB; extracted text stops at 30,000 characters; PDFs stop at 40 pages.
- Invalid, encrypted, unreadable, image-only, and unsupported documents fail with recovery guidance.
- Anonymous review files are parsed in memory and are not persisted. An approved user can explicitly add a
  CV version to their private library; those bytes are stored in a user-scoped Cloud Storage path.

### Job-page ingestion

- Only complete HTTPS URLs on the standard port are accepted; embedded credentials are rejected.
- DNS results must all be globally routable IP addresses.
- The connected peer address must be public and belong to the validated DNS result, closing the DNS
  rebinding gap for the production transport.
- Every redirect destination is revalidated and redirect depth is bounded.
- Responses are limited to 1 MiB and HTML, XHTML, or plain text.
- Remote HTML is parsed as data and is never rendered or executed.
- Timeouts and a manual-description fallback bound operational failure.

### Output and telemetry

- Jinja auto-escaping prevents submitted content from becoming executable HTML.
- The deterministic scorer has typed, versioned output and never creates candidate claims.
- Logs exclude CV text, job text, filenames, and full URLs. They contain only source, sizes, error types,
  timing, versions, aggregate counts, and opaque run IDs.
- The AI audit trail persists operational metadata only: tier, review type, status, model, selected advisor
  IDs, score/band, token counts, cost, and timing. It never stores CV text, job text, or generated prose.

### Identity and authorization

- Google identity is verified server-side. Every private career record is scoped by the verified subject.
- Workspace access is explicit and administrator-controlled; admin APIs require the configured admin role.
- Browser mutations reject cross-site requests and private API responses are marked `no-store`.

### AI spend and abuse controls

- Atomic reservations enforce per-tier monthly hard caps before a model call: USD 5 shared anonymous,
  USD 10 per approved identity, and a USD 50 project emergency ceiling.
- Anonymous and approved AI requests have separate burst limits. Security denials, repeated uploads, and
  AI bursts emit structured events for alerting.
- The admin control center reports cap usage and privacy-safe AI review history without exposing source data.

## Abuse and availability risks

- Public URL fetching can consume outbound bandwidth and connection slots. Cloud Run instance limits,
  response limits, timeouts, and scale-to-zero reduce but do not eliminate deliberate resource exhaustion.
- Broad public egress remains necessary for arbitrary job boards. A future allowlist would reduce SSRF and
  abuse exposure but would also reject legitimate employer sites.
- PDF parsing is CPU-bound. Page, byte, and character bounds limit work; process isolation is a future
  hardening option if public multi-user access is introduced.

## Deferred controls

- PDF parsing is bounded but not process-isolated; sandboxing and malware scanning remain future hardening.
- A formal least-privilege IAM audit and documented audit-metadata retention policy remain outstanding.
- Broad public launch would require stronger bot controls and a formal egress allow/deny policy.
