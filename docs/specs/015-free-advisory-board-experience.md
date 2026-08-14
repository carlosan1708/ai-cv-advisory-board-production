# 015 — Free advisory board experience

## Outcome

The anonymous experience should feel like an advisory board, not a generic CV score. A user uploads one CV, provides one job, chooses up to three specialist perspectives, sees the board visibly work, and receives a grounded report with distinct findings, safe tailoring moves, and interview preparation.

## Product principles

- Preserve the useful agency of the Streamlit prototype: the user chooses who reviews the application.
- Remove its operational cost: all selected specialists deliberate inside one bounded Gemini response rather than separate agent calls.
- Put board consensus and specialist reasoning before the deterministic score.
- Every strength, quote, and recommendation must be traceable to the supplied CV or explicitly identified as a gap.
- No anonymous source document, selection, or report is persisted.

## Journey

1. Upload a PDF/TXT CV or use the text fallback.
2. Add an HTTPS job link or paste the description.
3. Explicitly compose a panel of one to three advisors from six clear professional lenses. Nothing is preselected. Balanced, Builder, and Leadership presets are shortcuts that remain fully editable.
4. Submit once and see an honest board-in-session progress state.
5. Read the report in this order: canonical evidence match, AI availability status, panel consensus, specialist verdicts, tailoring plan, interview questions, score breakdown, evidence ledger, structured artifact.

## AI and cost architecture

- Advisor IDs are allowlisted and normalized server-side; client labels or prompts are never trusted.
- One `GeminiAiReviewer` call receives the selected advisor briefs and returns one strict `EvidenceReview` JSON object.
- The response contains at most three advisor findings, four tailoring moves, and four interview questions.
- Output is capped at 2,048 tokens and uses Gemini 2.5 Flash with thinking disabled.
- The existing shared USD 5 monthly ledger, project emergency ledger, and anonymous burst limit remain authoritative.
- Provider, rate-limit, and budget failures return the same report structure from the deterministic fallback with a visible disclosure.

## Security and grounding

- The browser sends only allowlisted advisor IDs; the server ignores unknown and duplicate IDs.
- An empty panel is rejected on both client and server; the server never silently substitutes a default panel.
- User CV and job text remain untrusted prompt data and cannot select a system instruction or advisor prompt.
- Model output is validated against bounded Pydantic schemas before rendering.
- Provider strings and lists are truncated to schema bounds before validation, and advisor findings are reordered against the server allowlist.
- Tailoring moves may change emphasis, order, clarity, or wording but may never add unsupported experience.
- Rendered content uses Jinja escaping and DOM `textContent`; no model HTML is executed.

## Acceptance criteria

- The progress rail exposes CV, Job, Board, and Report.
- Job validation succeeds before Board can open.
- The panel starts empty and makes the user's choice explicit.
- Balanced, Builder, and Leadership presets can be applied, adjusted, or cleared.
- One to three advisor cards can be selected; a fourth cannot be selected.
- The selected IDs survive validation errors and reach the reviewer in order.
- Submitting replaces the form with a visible, accessible board progress state.
- The report shows a distinct grounded finding for every selected advisor.
- Exactly one canonical numeric match score appears. AI panel confidence never competes with it.
- Provider degradation appears as a compact status after the primary result and does not render generic fallback advisor cards.
- The report includes safe tailoring moves and interview questions.
- The deterministic evidence baseline remains available and is visually secondary.
- Anonymous cost caps, no-persistence behavior, and security headers remain unchanged.
- Unit, API, and Playwright tests cover selection, validation, report content, progress, mobile overflow, and clean browser console output.
