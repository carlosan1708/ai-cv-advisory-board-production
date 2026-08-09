# Spec 007 — Career application pipeline

Status: Accepted for implementation

## Product correction

The CV review is a useful action, but it is not a complete product. The durable product is a lightweight
workspace that remembers where the user applied, which CV version was used, what happens next, and where AI
can remove repetitive work.

The default route becomes a career pipeline. A CV review is launched from an application or while adding one;
it is no longer the only thing the product can do.

## Primary workflow

1. Upload and label a CV version once.
2. Add a role with company, title, and job URL.
3. Attach the exact CV version used for that application.
4. Move the application through Interested, Applied, Interviewing, Offer, or Closed.
5. Record a next action and optional due date.
6. Ask AI to extract the role, compare evidence, or draft a truthful follow-up when useful.

Adding an application must take under one minute without AI and require only company, role, and status. Job
URL, CV version, date, next action, notes, and AI review remain optional.

## Information architecture

- `/` — concise product entry with Career workspace as the primary action.
- `/tracker` — application pipeline and progress funnel.
- `/workspace` — focused CV/job evidence review retained as a secondary tool.
- `/api/applications` — authenticated application CRUD.
- `/api/cv-versions` — authenticated immutable CV-version upload and listing.
- `/api/ai/review` — authenticated, budget-enforced Gemini review.

## Application model

Each application contains:

- opaque application ID and owner ID;
- company, role, optional public job URL, location, and source;
- status: `interested`, `applied`, `interviewing`, `offer`, or `closed`;
- optional applied date, next action, and next-action due date;
- optional CV-version ID;
- optional explainable fit score and AI summary;
- notes, created timestamp, and updated timestamp.

Moving a card updates only its status and updated timestamp. A status change is idempotent and remains safe to
retry.

## CV version contract

- A CV upload creates an immutable version; it never overwrites another version.
- PDF and UTF-8 TXT use the existing parsing limits and recovery messages.
- Metadata includes label, safe original filename, content type, byte count, hash, created timestamp, and
  owner ID.
- Bytes live in a private Cloud Storage object under the owner's prefix.
- Extracted text and metadata live in the owner's Firestore subcollection.
- An application stores the CV-version ID used at application time.
- A version referenced by an application is never silently deleted or replaced.
- Download requires the same verified owner as the version metadata.

## Pipeline interaction contract

- The Kanban board is the primary desktop visualization because status is the main changing property.
- Cards move through keyboard-accessible status controls; drag-and-drop is an enhancement, not the only path.
- A compact funnel shows counts from Applied through Offer and filters the board when selected.
- Closed applications remain available but do not dominate the default view.
- A fast-add drawer contains the minimum fields first and progressively reveals optional detail.
- Empty states teach one action and never simulate data.
- Mobile uses one status filter and a vertical card list instead of horizontal board scrolling.

## Identity and ownership

- Production API requests require a Google Identity Services ID token.
- The backend verifies issuer, audience, expiry, signature, and subject.
- The stable Google `sub` claim is the owner ID; email is display metadata only.
- Every repository lookup is scoped by owner ID before resource ID.
- Development and automated tests may use an explicit development identity mode; production may not.

## Gemini contract

- Model: `gemini-2.5-flash`, stable GA, global endpoint, thinking disabled.
- Gemini is used only for structured role extraction and a bounded evidence review.
- Input is limited to the selected CV text plus the current job description.
- Output is JSON matching a strict schema and limited to 1,024 output tokens.
- No Google Search, URL-context, code-execution, or other billable tool is enabled.
- The deterministic assessment remains available when Gemini is unavailable or the user budget is exhausted.
- AI output never becomes a candidate claim without explicit evidence from the attached CV.

## Per-user hard budget

- Default approved-user budget: USD 10.00 per verified user per calendar month, configurable by environment.
- Money is represented as integer micro-US dollars.
- Before a model request, the service atomically reserves the worst-case request cost in the user's monthly
  Firestore ledger.
- Parallel requests cannot reserve more than the remaining budget.
- After a successful response, actual token usage reconciles the reservation; unused reservation is released.
- Failed model requests release the reservation unless the provider reports billable usage.
- A request is rejected before Gemini when the maximum reservation would exceed the cap.
- The UI always shows used, reserved, and remaining AI budget.
- Project-level Google Cloud spend caps provide a second guardrail but do not replace per-user enforcement.

Gemini 2.5 Flash standard pricing assumptions are configuration, not hard-coded business logic:
USD 0.30 per million input tokens and USD 2.50 per million output/thinking tokens. A pricing-version field is
stored with each ledger entry so future model changes do not rewrite history.

## Persistence and deployment

- Firestore stores user-owned application, CV metadata/text, and monthly AI-ledger documents.
- Cloud Storage stores private CV bytes.
- Cloud Run uses a dedicated service account with only Firestore user, Vertex AI user, log writer, and
  bucket-scoped object access.
- Local tests use in-memory repository, file store, identity verifier, and Gemini adapter implementations.
- No provider call, credential, Firestore database, or bucket is required for the deterministic test suite.

## Observability

Structured events include application created/status changed, CV version created, AI reservation accepted or
rejected, Gemini request completed/failed, token counts, estimated/actual micro-USD, model, pricing version,
duration, and opaque user/application/request IDs.

Events never include CV text, job text, notes, filenames, email, full job URL, ID tokens, or model output.

## Acceptance criteria

- A signed-in user can add, edit, move, filter, and reopen applications.
- A user can upload multiple immutable CV versions and see the version attached to each card.
- No user can read or mutate another user's application, CV version, or cost ledger.
- The board remains usable without drag-and-drop and at 390px width.
- Funnel counts update after a status move without a full reload.
- AI calls stop before exceeding USD 5.00 of reserved plus settled monthly spend.
- Concurrent reservations cannot pass the cap.
- Provider failure releases reservation and leaves the application usable.
- Unit, repository-contract, web, security, evaluation, and Playwright suites pass without paid services.
- Production regression covers sign-in, CV version upload, application creation, status move, attachment
  visibility, deterministic review fallback, mobile overflow, and clean console output.
