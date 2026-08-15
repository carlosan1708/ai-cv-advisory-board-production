# Spec 016 — README product demos

## Goal

Show the product's real capabilities directly in the repository without requiring a visitor to sign in, spend AI allowance, or trust a static mockup.

## Portfolio consistency

The README follows the same case-study rhythm as
[`carlosan1708/trip-itinerary-displayer`](https://github.com/carlosan1708/trip-itinerary-displayer):

1. Animated product hero, title, concise value proposition, author statement, live demo, and stack badges.
2. AI engineering highlights and a compact system flow before the general feature inventory.
3. Primary product capabilities and additional GIF walkthroughs.
4. Stack, local setup, quality gates, tests, architecture, security, deployment, and the engineering trail.

Consistency applies to portfolio information hierarchy and evidence quality. It does not require the two
products to share branding, implementation choices, access policy, repository visibility, or licensing.

## Capture scenarios

1. **Free advisory-board review**
   - Start at the document-first free workflow.
   - Open the deterministic synthetic sample.
   - Show the evidence-match score and explanation.
   - Show the selected specialist consensus and findings.
   - Show safe tailoring, interview preparation, and the evidence ledger.
2. **Application tracker and AI expert panel**
   - Start at the application dashboard with synthetic applications in multiple stages.
   - Show the funnel and CV-version attachment on each card.
   - Move one application and show the funnel update.
   - Focus the Interviewing stage.
   - Open the AI expert panel and show its deterministic three-lens result.
3. **CV library and immutable revisions**
   - Start with two synthetic CV versions.
   - Run a standalone deterministic CV review.
   - Open the revision editor.
   - Save a third version and leave the original intact.

## Privacy and cost constraints

- Captures must use synthetic names, companies, roles, CV content, and job-search actions.
- Captures run against the local development adapters and deterministic reviewers.
- No Google identity, production career record, personal document, or paid model call may appear.
- The GIFs must not imply that deterministic sample prose came from Gemini.

## Media contract

- Store the files under `docs/assets/demo/` with stable descriptive filenames.
- Render at 960 × 540 so text remains legible in GitHub's README view.
- Keep each GIF below 1.5 MB and the combined set below 3 MB.
- Keep each loop at or below 12 seconds.
- Use a generated palette and bounded color count to avoid unnecessary repository weight.
- Provide meaningful README alt text and make each image link to the corresponding production route.

## Acceptance criteria

- GitHub can render all three relative GIF paths without an external image host.
- The free review includes the score, specialist panel, action plan, and evidence ledger.
- The tracker includes multiple stages, a live state change, a focused view, and an expert-panel result.
- The CV library includes standalone review, editing, and a visible new immutable version.
- Every captured person, company, document, and action is synthetic.
- The primary free-review GIF appears above the title as the repository hero; the tracker and CV-library GIFs
  remain in a clearly labelled additional-demo section.
- The README identifies the product value, live demo, author, AI engineering decisions, stack, test strategy,
  architecture, security controls, deployment target, and spec trail in a consistent portfolio narrative.
- Automated tests remain unchanged and green because documentation capture does not alter product behavior.
