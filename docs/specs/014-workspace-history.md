# 014 — Read-only workspace history

## Outcome

An approved member can archive the complete active job-search workspace and immediately begin with an empty dashboard and CV library. History retains the archived applications, exact CV versions, file objects, version lineage, and application-to-CV relationships for later reference. An archive is never restored or merged into the active workspace.

## User experience

- Dashboard navigation exposes **History**.
- **Archive & start fresh** shows the exact application and CV-version counts before proceeding.
- The member gives the archive a recognizable name and explicitly confirms that active views will become empty.
- **Past workspaces** lists each archive with its date and counts.
- **View** opens a read-only detail showing past applications, their status, and the exact attached CV label.
- Archived CV files remain downloadable from the detail view.
- Viewing history never changes, replaces, or adds records to the active workspace.
- AI allowances and usage history are not reset by workspace archiving.

## Storage design

Applications and CV metadata have an optional `archive_id`. Active repository methods return only records without an archive ID. Archiving assigns one owner-scoped archive ID to all active records in a single Firestore batch and creates a `workspace_archives` manifest containing counts and creation time.

Cloud Storage objects are not copied or deleted. Their immutable owner/version paths remain unchanged. Read-only archive queries filter records by both verified owner and archive ID.

## Security and integrity rules

- Every archive API derives its owner from the verified Google identity; the client cannot submit an owner ID.
- Another owner receives neither archive metadata nor a distinguishable download response.
- Archived records remain inaccessible through active application, CV, download, and AI-review endpoints.
- Archived detail endpoints expose CV metadata without extracted CV text.
- Archived CV downloads verify owner, archive membership, and version ID before reading bytes.
- No restore, merge, mutation, or archived AI-review endpoint exists.
- One archive is limited to 450 application and CV records so the manifest and mutations fit safely within Firestore's 500-write batch limit.

## API

- `GET /api/workspace-archives` — list the current owner's archive manifests.
- `POST /api/workspace-archives` — archive all active applications and CV versions.
- `GET /api/workspace-archives/{archive_id}` — inspect applications and CV metadata in one owner-scoped archive.
- `GET /api/workspace-archives/{archive_id}/cv-versions/{cv_version_id}/download` — download an archived CV after archive-membership verification.

## Acceptance criteria

- Applications and CVs disappear from active APIs together after archive.
- Original IDs, relationships, metadata, and file bytes remain visible through read-only History.
- Application rows identify the exact archived CV version they reference.
- Cross-owner archive detail and CV downloads return HTTP 404.
- Viewing an archive leaves current applications and CV versions unchanged.
- The History UI works on desktop and mobile navigation.
- Unit, API, and Playwright tests cover archive, empty state, history detail, attached CV identity, download, owner isolation, and active-workspace immutability.
