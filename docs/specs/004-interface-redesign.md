# Spec 004 — Advisory workspace interface

Status: Implemented

## Context

The initial interface proved the end-to-end assessment flow but presented it as an editorial landing page. The product it replaces is a guided Streamlit workflow with visible stages for setup, CV input, job context, team selection, and results. The production replacement needs to preserve that sense of progress while looking like a trustworthy career-analysis workspace rather than a marketing concept.

## Design direction

- Calm, professional application shell with a compact top bar and persistent workflow navigation.
- Neutral canvas and white working surfaces; deep navy navigation; muted blue as the only primary action accent.
- No neon, acid, coral, or oversized display typography.
- Dense enough for serious work while retaining clear spacing and hierarchy.
- Evidence and privacy language remains visible at the point of use.
- Results prioritize traceability: score limitation, component breakdown, source evidence, gaps, and structured output.

## Information architecture

1. Candidate profile — CV evidence.
2. Target role — job requirements.
3. Advisory review — deterministic comparison.
4. Recommendations — supported evidence and truthful gaps.

The current vertical slice collects steps 1 and 2 together for speed. The progress rail establishes the structure for later file upload, provider configuration, specialist selection, and richer results without presenting inactive controls as implemented features.

## Interaction requirements

- A synthetic-data path is available without an API key.
- Both text inputs and the primary review action are visible in the first workspace view on desktop.
- Input state remains present after assessment.
- Results appear in the same document and retain the disclaimer beside the score.
- No recommendation may imply experience absent from the CV.
- All controls have semantic labels and a visible keyboard focus treatment.

## Responsive behavior

- At tablet widths, the vertical workflow rail becomes a compact horizontal progress indicator.
- At mobile widths, input and result columns stack and all actions become full width.
- No viewport at or above 390 CSS pixels may have horizontal page overflow.

## Visual regression contract

- The stylesheet must use a same-origin path (`/static/app.css`).
- The body background resolves to `rgb(246, 247, 251)`.
- The page must not fall back to Times New Roman.
- Playwright covers the sample review, custom review, structured result, and mobile overflow.

