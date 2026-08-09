# Threat model

## Assets

- CV bytes, extracted text, contact information, and filenames.
- Job URLs, descriptions, and the candidate's job-search intentions.
- Integrity of findings and recommendations.
- Provider credentials in future model-backed phases.

## Trust boundaries

Browser input, uploaded documents, remote job pages, redirects, and future model output are untrusted.
Application logs and downloadable artifacts are separate disclosure surfaces.

## Current controls

### CV ingestion

- PDF and UTF-8 TXT are the only accepted formats.
- Reads stop after 5 MiB; extracted text stops at 30,000 characters; PDFs stop at 40 pages.
- Invalid, encrypted, unreadable, image-only, and unsupported documents fail with recovery guidance.
- Files are parsed in memory and are not persisted.

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
- No persistence or user-built authentication exists in this private single-user phase.

## Abuse and availability risks

- Public URL fetching can consume outbound bandwidth and connection slots. Cloud Run instance limits,
  response limits, timeouts, and scale-to-zero reduce but do not eliminate deliberate resource exhaustion.
- Broad public egress remains necessary for arbitrary job boards. A future allowlist would reduce SSRF and
  abuse exposure but would also reject legitimate employer sites.
- PDF parsing is CPU-bound. Page, byte, and character bounds limit work; process isolation is a future
  hardening option if public multi-user access is introduced.

## Deferred controls

- Before live LLM use: explicit data delimiters, typed outputs, evidence citations, claim validation, bounded
  retries, provider privacy review, and adversarial prompt-injection evaluations.
- Before persistence or multi-user access: identity-derived ownership, authorization tests, encryption,
  retention/deletion policy, and audit events.
- Before broad public launch: rate limiting, abuse monitoring, malware scanning, and a formal egress policy.
