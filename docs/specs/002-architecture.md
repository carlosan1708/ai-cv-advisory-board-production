# Spec 002 — Architecture

Status: Accepted

## Boundaries

```text
Browser -> FastAPI web adapter -> AssessmentService -> domain scoring policy
                                      |-> structured event logger
```

- Domain code has no FastAPI, storage, browser, or model-provider imports.
- Application services orchestrate domain policies.
- Web code translates HTTP inputs and outputs.
- External AI will be introduced behind an adapter after a deterministic evaluation baseline exists.

## Deployment modes

- `demo`: synthetic inputs; no external calls or persistence.
- `local`: user-supplied text; no persistence in v0.1.
- `production`: Cloud Run; same stateless behavior until an authenticated identity boundary is implemented.

## Data classification

CV and job text are sensitive transient content. They may be held in request memory but are never logged or persisted in v0.1. Only lengths, hashes, run IDs, timing, versions, and aggregate counts may enter logs.

