# Spec 001 — Product vertical slice

Status: Accepted

## Problem

Job seekers need actionable CV feedback without fabricated experience or an opaque pseudo-ATS score.

## User outcome

Given a CV and job description, the system returns an explainable match assessment containing a bounded score, detected requirements, evidence found in the CV, gaps, warnings, and safe recommendations.

## Functional requirements

- FR-01: Accept pasted CV and job-description text.
- FR-02: Reject empty or excessively large inputs.
- FR-03: Offer a fully synthetic demo.
- FR-04: Produce versioned structured output.
- FR-05: Associate every recommendation with a detected gap; never invent candidate claims.
- FR-06: Make limitations visible next to the score.
- FR-07: Provide a downloadable JSON result.

## Non-goals for v0.1

- Authentication and persistence.
- Scraping arbitrary job URLs.
- Generating a rewritten CV.
- Calling a live LLM.

These are intentionally excluded until identity, SSRF protection, evaluation, and evidence-validation contracts exist.

## Acceptance criteria

- The demo completes in under one second locally.
- Inputs over configured limits return HTTP 422.
- Output validates against `Assessment` schema version `1.0`.
- Score is between 0 and 100 and decomposes into documented components.
- Browser tests cover home, demo, custom analysis, validation, and JSON export.

