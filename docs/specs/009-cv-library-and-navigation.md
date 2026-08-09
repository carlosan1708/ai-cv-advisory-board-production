# Spec 009: CV library and workspace navigation

## Product model

The private workspace has three primary destinations:

1. **Dashboard** is the default signed-in page and owns application tracking.
2. **CV Library** owns source documents, standalone reviews, editing, and immutable versions.
3. **Free Review** remains the public, session-only CV-to-job workflow.

Administrators additionally see **Access**. Desktop uses a persistent top-level menu; mobile uses a fixed three-item navigation bar.

## CV library behavior

- A CV exists independently of an application.
- PDF and TXT uploads are parsed and stored as immutable source versions.
- An approved member can request a standalone AI audit of clarity, evidence, structure, specificity, and seniority signaling.
- Editing never overwrites a stored document. The extracted text opens in an editor and saving creates a new TXT version with `parent_version_id` lineage.
- Every version remains downloadable and attachable to future applications.

## Application comparison

- An application can attach any saved CV version.
- An attached version exposes **Review attached CV** directly on the application card.
- The review dialog clearly identifies the application and CV version.
- A saved public job link is fetched server-side; a pasted description is available when the posting cannot be fetched or no link exists.
- The resulting evidence score and summary are stored on the application, while the CV version remains immutable.

## Acceptance criteria

- `/dashboard` is the canonical application dashboard; `/tracker` remains a compatible alias.
- `/cvs` is protected by the same approval boundary as application data.
- Standalone CV review does not require an application or job description.
- Saving edited text creates a child version and leaves the parent unchanged.
- Application review works with either a public job URL or pasted description.
- Desktop and mobile navigation always expose Dashboard, CV Library, and Free Review.
- AI calls for approved members remain unrestricted at the application layer and emit token/cost observability without document contents.

## Regression coverage

- Unit/API tests cover standalone scoring, private CV detail, child-version creation, lineage, and independent review.
- Browser tests cover uploading, reviewing, editing, saving, attaching, application comparison, navigation, and clean browser consoles.
