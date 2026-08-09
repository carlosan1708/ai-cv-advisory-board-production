# Spec 010: Dashboard expert panel and persistent session

## Problem

The private workspace must feel like one coherent product. Moving from the dashboard to the CV library or access management must not appear to sign the member out. CV analysis must use job-seeker language and start from the dashboard instead of exposing an internal concept such as “evidence review.”

## Navigation and session

- A verified Google ID token is exchanged for a secure, HTTP-only `advisory_session` cookie.
- The cookie uses `SameSite=Lax`, is secure outside development, and expires after one hour.
- Every protected API accepts the same verified identity from either the cookie or the in-memory bearer token used immediately after Google sign-in.
- Dashboard and CV Library are the primary member destinations. Administrators additionally see Access.
- The public free review is reached from the public landing experience; it is not mixed into the private workspace menu.

## Dashboard AI expert panel

- The dashboard contains one prominent **AI Expert Panel** action above the application funnel.
- The member first chooses an immutable CV version from the library.
- **Review this CV** evaluates the document independently of an opportunity.
- **Compare with an application** selects a tracked application and optionally accepts pasted job text when its public link is absent or unavailable.
- Application fields remain hidden until the comparison mode is selected.
- The selected CV version becomes the version attached to that comparison; the source document is never mutated.
- One bounded structured model call is presented through three practical lenses: Recruiter, Hiring Manager, and Technical Reviewer. The interface must not imply three separate billable model calls.
- Results may identify unsupported or missing evidence but must never invent experience.

## Access and cost policy

- Public, no-login AI usage consumes the shared monthly USD 5 pool and stops before the configured hard cap.
- Administrator-approved members have no in-app AI usage cap.
- All AI calls retain model, token, latency, status, and estimated-cost telemetry without logging CV or job-description contents.

## Acceptance criteria

- A member can sign in once, visit Dashboard, CV Library, and Access, and remain signed in until the verified credential expires or logout is requested.
- Logout clears the session cookie.
- The dashboard explains the review choices without using “evidence review” as a product label.
- Standalone review requires only a saved CV.
- Application comparison requires a saved CV and tracked application and supports a pasted job description fallback.
- The result visibly separates Recruiter, Hiring Manager, and Technical Reviewer feedback.
- Desktop and mobile layouts keep the application dashboard primary and expose the expert panel in one action.

## Regression coverage

- API tests verify cookie creation, HTTP-only attributes, cookie authentication, expiration behavior through token verification, and logout deletion.
- Browser tests verify private navigation, CV upload/versioning, standalone panel review, all three lenses, exact-version application attachment, application comparison, and clean browser consoles.
- Static checks and unit/API coverage remain mandatory before deployment.
