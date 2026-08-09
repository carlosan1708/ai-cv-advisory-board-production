# Spec 002 — Architecture

Status: Accepted

## Boundaries

```text
Browser -> FastAPI web adapter -> CV parser -----------\
                            |-> safe job-page fetcher ---+-> AssessmentService -> scoring policy
                            |-> structured event logger /
```

- Domain code has no FastAPI, storage, browser, or model-provider imports.
- Application services orchestrate domain policies.
- Web code translates HTTP inputs and outputs.
- Document ingestion is an adapter boundary: PDF/TXT parsing is bounded and job-page reads are public,
  HTTPS-only, redirect-aware, byte-limited, and content-type-limited.
- External AI will be introduced behind an adapter after a deterministic evaluation baseline exists.

## Deployment modes

- `demo`: synthetic inputs; no external calls or persistence.
- `local`: user-supplied text; no persistence in v0.1.
- `production`: Cloud Run; same stateless behavior until an authenticated identity boundary is implemented.

## Data classification

CV files, extracted text, job URLs, and job descriptions are sensitive transient content. They may be held
in request memory but are never logged or persisted. Only source type, byte/character counts, error types,
run IDs, timing, versions, and aggregate counts may enter logs.
