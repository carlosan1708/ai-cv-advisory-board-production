# Spec 004 — Welcome and guided advisory review

Status: Implemented

## Context

The product replaces a Streamlit application whose strongest qualities are its approachable welcome screen, explicit board concept, and sequential workflow. A first production interface collapsed the experience into a dense form and then a generic dashboard. Both reduced clarity and emotional appeal even though they improved implementation quality.

The replacement must improve the original without erasing its identity.

## Product principles

- Welcome before asking for work: explain the board, value, safeguards, and flow before showing inputs.
- One decision at a time: CV first, target role second, findings last.
- Preserve the board metaphor: recruiting, hiring, and technical perspectives remain visible.
- Evidence over decoration: visual hierarchy supports the review rather than competing with it.
- Warm and credible: neutral paper surfaces, charcoal typography, and one muted plum accent.
- No neon palette, dark dashboard rail, oversized SaaS chrome, or inactive navigation.

## Information architecture

### Welcome

1. Product promise and primary action.
2. Advisory-board preview.
3. Evidence, truthfulness, and privacy safeguards.
4. Three concrete benefits.
5. Four-stage review explanation.

### Guided workspace

1. Add CV content.
2. Add the target role.
3. Run the deterministic board review.
4. Inspect evidence, gaps, component scores, and structured output.

## Interaction requirements

- `GET /` renders the welcome experience.
- `GET /workspace` starts the guided review at the CV step.
- Continuing without CV text uses native constraint feedback and does not advance.
- Input state remains in the document after assessment.
- A synthetic sample is available from both welcome and workspace.
- Score limitations remain beside the score.
- Every recommendation is derived from a detected gap.

## Responsive behavior

- The welcome hero stacks below 900 CSS pixels.
- The progress indicator remains visible on mobile without its secondary labels.
- Input and finding panels use a single column on mobile.
- No page may overflow horizontally at 390 CSS pixels.

## Regression contract

- Styles and behavior load from same-origin `/static/app.css` and `/static/app.js`.
- The welcome background resolves to `rgb(251, 250, 248)`.
- Browser tests cover welcome, synthetic review, progressive custom review, structured results, and mobile overflow on welcome and workspace.
- Browser console warnings and errors are empty in the final production regression.
