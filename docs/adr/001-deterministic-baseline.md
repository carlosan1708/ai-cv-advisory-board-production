# ADR 001 — Establish a deterministic baseline before adding Gemini

Status: Accepted

## Decision

The first production slice uses a deterministic, versioned match policy. Gemini will later enrich explanations behind an adapter, but will not own the authoritative score or be allowed to add unsupported candidate claims.

## Rationale

This gives the project a stable oracle for tests, evaluation and UI development; keeps CI free of paid credentials; exposes limitations honestly; and makes later model improvements measurable instead of anecdotal.

