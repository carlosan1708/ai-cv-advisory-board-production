# Spec 006 — Document-first review flow

Status: Implemented

## Correction

The prior redesign improved visual consistency while making the product less useful. It replaced the original CV upload with a large textarea, removed job-link ingestion, and added too much explanatory content to the start page. Those are regressions, not simplifications.

This revision restores the task model users already understand: bring a CV file, bring the job link, then review the board's findings. Manual text remains available as a recovery path rather than the primary experience.

## Product principles

- Ask for the artifact the user already has. A CV is normally a file, not clipboard text.
- Ask for the reference the user already has. A target role is normally a public job URL.
- Keep recovery close. PDF/TXT parsing and public-page extraction can fail, so manual paste is always one disclosure away.
- Reveal one decision at a time. Welcome, CV, target, and findings are distinct states.
- Explain only what affects the current decision. Product marketing does not compete with the task.

## Welcome contract

The complete welcome experience fits in one normal desktop viewport and contains:

1. Product name and privacy state.
2. A concise outcome statement.
3. One primary action and one synthetic-demo action.
4. Three compact steps: upload CV, add job link, inspect findings.
5. A short limitation statement for the deterministic baseline.

The welcome page does not contain a simulated dashboard, a second workflow section, or repeated benefit copy.

## CV stage

- Primary control: file upload accepting PDF and UTF-8 TXT.
- Maximum file size: 5 MiB.
- Maximum extracted text: 30,000 characters.
- Maximum PDF page count: 40.
- The selected filename and size are visible before continuing.
- Drag-and-drop and file-picker interaction share the same validation.
- A collapsed "Paste text instead" fallback remains available.
- Empty, unsupported, encrypted, unreadable, image-only, oversized, or excessively long files produce specific recovery guidance.

## Target stage

- Primary control: HTTPS job URL.
- The server accepts public destinations only.
- Redirect destinations are revalidated.
- Loopback, link-local, private, multicast, reserved, credential-bearing, non-HTTPS, and non-standard-port URLs are rejected.
- Responses are bounded to 1 MiB and must be HTML or plain text.
- Extraction prefers JobPosting JSON-LD and common job-description containers.
- A collapsed "Paste description instead" fallback is always available.
- Manual description takes precedence when both URL and text are present, enabling immediate recovery from a blocked page.

## Privacy and security contract

- CV bytes and extracted CV text are processed in memory and never sent to the job page.
- The public job URL is fetched by the application using a bounded timeout and a neutral user agent.
- Logs contain byte counts and outcome metadata only; they never contain CV text, job text, filenames, or full URLs.
- URL validation occurs before every request and redirect.
- HTML is parsed as data and never executed.
- Existing output escaping and no-persistence rules remain in force.

## Interaction contract

- The CV stage cannot advance until a supported file or pasted text is present.
- The target stage cannot submit until a job URL or pasted description is present.
- Returning to the CV stage preserves the selected file and pasted fallback.
- Server errors reopen the stage that needs attention.
- If job extraction fails, the parsed CV text is preserved for the retry and the manual job-description fallback opens automatically.
- Findings and structured JSON remain unchanged in purpose.

## Regression contract

- Unit tests cover TXT/PDF parsing, size and page limits, empty/image-only documents, URL normalization, private-address rejection, redirect revalidation, content limits, JSON-LD extraction, selector extraction, and fetch failures.
- Web tests cover file upload, URL ingestion through an injected fetcher, manual fallback precedence, error-stage recovery, and legacy text/API compatibility.
- Playwright covers the quiet welcome, file selection, invalid-file feedback, job-link-first layout, manual recovery, findings, mobile overflow, keyboard flow, and clean browser console output.
- Production regression covers a real TXT upload with manual job fallback plus the synthetic demo. Network extraction correctness is verified deterministically before deployment and production URL failures remain recoverable by design.

## Implementation evidence

- `src/advisory/ingestion.py` owns bounded document parsing, public-URL validation, connected-peer
  verification, redirects, response limits, and extraction.
- `src/advisory/templates/index.html`, `app.css`, and `app.js` implement the progressive upload/link flow.
- `tests/test_ingestion.py` and `tests/test_web.py` cover parser, fetcher, security, and recovery contracts.
- `tests_e2e/test_app.py` covers 12 browser scenarios across desktop, mobile, upload, fallback, findings,
  export, and console health.
- `docs/THREAT_MODEL.md` and `docs/OPERATIONS.md` record the security and operating consequences.
