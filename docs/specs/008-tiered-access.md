# Spec 008: tiered access and AI entitlement

## Outcome

The product has two explicit entry modes:

1. **Free AI review** — anonymous, session-only CV-to-job analysis using Gemini. All anonymous traffic shares one monthly USD 5 application-level budget. The server reserves worst-case request cost atomically before calling the model. When the pool is exhausted or Gemini fails, the deterministic evidence engine still returns a useful result.
2. **Private workspace** — Google-authenticated application tracking, immutable CV versions, and AI evidence reviews. Access is available only to emails approved by the administrator. Each approved member has a USD 10 monthly AI allowance.

## Security boundary

- Google ID tokens are verified server-side.
- Every private repository and AI endpoint checks approval; hiding UI is never the authorization control.
- The configured administrator email bootstraps the admin role.
- Admins can pre-approve an email or approve/reject a pending request.
- Anonymous uploads and extracted text are not persisted.
- The anonymous budget key is global (`anonymous-free-tier`) so clearing browser state cannot reset the USD 5 ceiling.

## Acceptance criteria

- `/` clearly presents the free and private paths without an authentication wall.
- `/workspace` accepts PDF/TXT CV input and a public job URL or pasted description.
- A successful free review contains deterministic findings and a grounded AI review.
- The free AI provider is never called when its worst-case reservation does not fit under USD 5.
- `/tracker` remains locked for unapproved Google identities and offers an access-request action.
- All `/api/applications*` and `/api/cv-versions*` calls reject unapproved identities.
- `/admin` lists requests and supports pre-approval, approval, and rejection.
- `/api/applications/{id}/ai-review` does not consult or decrement the free-tier ledger.
- AI usage emits completion/failure events with tokens, estimated cost, tier, and duration; no CV or job content is logged.

## Regression coverage

- Unit tests cover user/project budget reservation and reconciliation, identity verification, and access lifecycle.
- API tests cover the two-mode page, tier hard caps, burst controls, and admin authorization.
- Playwright covers desktop/mobile mode selection, the free upload flow, private sign-in gate, pipeline interactions, and browser console errors.
