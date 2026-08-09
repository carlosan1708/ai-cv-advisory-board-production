# Spec 005 — Product interface recovery

Status: Accepted for implementation

## Why this revision exists

The previous interface was visually styled but product-light. It used an editorial serif, muted plum and sage accents, very small supporting text, and a landing-page structure that made the application feel like a generic career SaaS template. The advisory-board concept was decorative rather than operational, the four-step indicator did not match the two input steps, and findings did not clearly separate advisor perspectives from raw scoring components.

The original Streamlit application was visually basic, but it did three important things well: it made the board concept immediately understandable, showed a sequential task, and kept the primary action obvious. This revision preserves those strengths without copying Streamlit's default appearance.

## Product outcome

A visitor should understand the product, begin a review, complete it, and interpret the result without needing instructions outside the interface. The experience should feel like a focused professional tool, not a marketing site or a decorative dashboard.

## Design direction

- Use a neutral white and cool-gray system with one saturated blue product accent.
- Use a readable sans-serif stack throughout; no editorial serif display type.
- Keep body text at 14–18 CSS pixels. Metadata may not be smaller than 12 CSS pixels.
- Prefer solid surfaces, clear borders, and restrained shadows over gradients or ornamental layers.
- Use color to communicate action and state, not personality.
- Keep the board visible as three explicit review lenses: recruiter, hiring manager, and technical reviewer.

## Information architecture

### Welcome

1. Product name, status, and a direct start action.
2. One-sentence outcome: pressure-test a CV against a role using traceable evidence.
3. A concrete sample board briefing, not an abstract illustration.
4. Three outputs: role coverage, advisor lenses, and an evidence-backed action plan.
5. Privacy and scoring limitations stated before the user submits content.

### Review workspace

The progress model has exactly three stages:

1. Evidence — paste the CV content to evaluate.
2. Target — paste the job description.
3. Findings — inspect score, advisor lenses, evidence, gaps, and export.

There is no fictional fourth interactive step. The board review happens during the transition from Target to Findings.

### Findings

1. An honest alignment summary whose wording changes by score band.
2. The heuristic limitation adjacent to the score.
3. Three advisor-lens cards tied to documented score components.
4. A requirement-by-requirement evidence ledger with supported and missing states.
5. A prioritized truthful action list.
6. A downloadable structured JSON assessment.

## Interaction requirements

- CV input is required before moving to Target.
- Back navigation preserves the CV text.
- Both text areas expose a live character count and the 30,000-character limit.
- Submitting a valid role produces findings on the same request.
- The synthetic review remains available from Welcome and Workspace.
- Findings provide both a new-review action and a JSON download.
- Focus moves to the new stage heading when the user advances or returns.
- Motion respects `prefers-reduced-motion`.

## Responsive requirements

- No horizontal overflow at 390 CSS pixels on Welcome, either input stage, or Findings.
- The header reduces to the product mark and primary action on narrow screens.
- Progress labels remain readable; secondary descriptions may collapse.
- Advisor lenses and evidence items use one column below 760 CSS pixels.
- Primary actions span the available width on narrow screens.

## Accessibility requirements

- Every page has one primary `h1`.
- Header, navigation, main, complementary, and footer landmarks are named where needed.
- Interactive controls have visible focus states.
- Status is never communicated by color alone.
- Form errors use `role="alert"`.
- The score disclaimer is programmatically associated with the score summary.
- Contrast meets WCAG AA for normal text.

## Regression contract

- Unit and integration tests cover all routes and API error contracts.
- Playwright covers Welcome, sample findings, custom findings, validation, backward navigation, character counts, JSON download, mobile overflow, and browser console cleanliness.
- The production regression repeats the primary demo and custom-review flows against the deployed Cloud Run URL.
- The final deployed revision must return HTTP 200 for `/` and `/healthz`.

