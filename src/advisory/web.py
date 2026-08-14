from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from advisory.access import (
    AccessControl,
    AccessDecision,
    AccessInvite,
    FirestoreAccessControl,
    InMemoryAccessControl,
)
from advisory.advisors import (
    ADVISOR_BY_ID,
    ADVISORS,
    DEFAULT_ADVISOR_IDS,
    advisor_context,
    normalize_advisor_ids,
)
from advisory.ai import (
    AiReviewer,
    BudgetedAiService,
    BudgetedCvService,
    CvReviewer,
    DeterministicAiReviewer,
    DeterministicCvReviewer,
    EvidenceReview,
    GeminiAiReviewer,
    GeminiCvReviewer,
)
from advisory.auth import IdentityVerifier, UserIdentity
from advisory.budget import BudgetExceededError, BudgetLedger, InMemoryBudgetLedger
from advisory.career import ApplicationCreate, ApplicationUpdate
from advisory.career_repository import (
    CareerRepository,
    EmptyWorkspaceError,
    InMemoryCareerRepository,
    NotFoundError,
)
from advisory.demo import DEMO_CV, DEMO_JOB
from advisory.domain import Assessment
from advisory.google_persistence import FirestoreBudgetLedger, GoogleCareerRepository
from advisory.ingestion import (
    CvDocumentError,
    CvDocumentParser,
    JobDescriptionError,
    JobDescriptionFetcher,
)
from advisory.observability import emit
from advisory.rate_limit import RateLimitExceededError, SlidingWindowRateLimiter
from advisory.service import AssessmentService, InputError
from advisory.settings import get_settings
from advisory.tracker_service import TrackerService

BASE_DIR = Path(__file__).resolve().parent
settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")


def _expected_origin(request: Request) -> str:
    if settings.environment == "production":
        return settings.public_origin.rstrip("/")
    return str(request.base_url).rstrip("/")


@app.middleware("http")
async def browser_security(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        fetch_site = request.headers.get("sec-fetch-site", "").casefold()
        origin = request.headers.get("origin", "").rstrip("/")
        if fetch_site == "cross-site" or (origin and origin != _expected_origin(request)):
            emit(
                "security.cross_site_blocked",
                method=request.method,
                path=request.url.path,
                fetch_site=fetch_site or "missing",
            )
            return JSONResponse(status_code=403, content={"detail": "Cross-site request blocked"})

    response = await call_next(request)
    if response.status_code in {401, 403}:
        emit(
            "security.access_denied",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://accounts.google.com/gsi/client; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https://*.googleusercontent.com; "
        "connect-src 'self' https://accounts.google.com/gsi/; "
        "frame-src https://accounts.google.com/gsi/; "
        "font-src 'self'; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/health"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
identity_verifier = IdentityVerifier(settings.auth_mode, settings.google_oauth_client_id)
admin_emails = {email.strip().casefold() for email in settings.admin_emails.split(",") if email.strip()}
if settings.repository_backend == "firestore":
    career_repository: CareerRepository = GoogleCareerRepository(settings.gcp_project, settings.cv_bucket)
    free_budget_ledger: BudgetLedger = FirestoreBudgetLedger(
        settings.gcp_project, settings.ai_monthly_limit_micro_usd
    )
    member_budget_ledger: BudgetLedger = FirestoreBudgetLedger(
        settings.gcp_project, settings.member_ai_monthly_limit_micro_usd
    )
    project_budget_ledger: BudgetLedger = FirestoreBudgetLedger(
        settings.gcp_project, settings.project_ai_monthly_limit_micro_usd
    )
    access_control: AccessControl = FirestoreAccessControl(settings.gcp_project, admin_emails)
else:
    career_repository = InMemoryCareerRepository()
    free_budget_ledger = InMemoryBudgetLedger(settings.ai_monthly_limit_micro_usd)
    member_budget_ledger = InMemoryBudgetLedger(settings.member_ai_monthly_limit_micro_usd)
    project_budget_ledger = InMemoryBudgetLedger(settings.project_ai_monthly_limit_micro_usd)
    access_control = InMemoryAccessControl(admin_emails, allow_all=settings.auth_mode == "development")

ai_rate_limiter = SlidingWindowRateLimiter()
PROJECT_BUDGET_OWNER = "_project-emergency-cap"


def owner_id(request: Request) -> str:
    identity = identity_verifier.verify(request)
    access_control.require_access(identity)
    return identity.subject


def identity(request: Request) -> UserIdentity:
    return identity_verifier.verify(request)


class SessionCredential(BaseModel):
    credential: str


class ArchiveWorkspaceRequest(BaseModel):
    label: str


def service() -> AssessmentService:
    return AssessmentService(max_input_chars=settings.max_input_chars)


def cv_document_parser() -> CvDocumentParser:
    return CvDocumentParser(
        max_file_bytes=settings.max_upload_bytes,
        max_chars=settings.max_input_chars,
    )


def job_description_fetcher() -> JobDescriptionFetcher:
    return JobDescriptionFetcher(
        max_response_bytes=settings.max_job_page_bytes,
        max_chars=settings.max_input_chars,
    )


def tracker_service() -> TrackerService:
    return TrackerService(career_repository, cv_document_parser())


def ai_reviewer() -> AiReviewer:
    reviewer: AiReviewer
    if settings.environment == "production":
        reviewer = GeminiAiReviewer(
            project=settings.gcp_project,
            location=settings.gcp_location,
            model=settings.gemini_model,
        )
    else:
        reviewer = DeterministicAiReviewer()
    return reviewer


def free_ai_service() -> BudgetedAiService:
    return BudgetedAiService(
        ai_reviewer(),
        free_budget_ledger,
        emergency_ledger=project_budget_ledger,
        emergency_owner_id=PROJECT_BUDGET_OWNER,
    )


def member_ai_service() -> BudgetedAiService:
    return BudgetedAiService(
        ai_reviewer(),
        member_budget_ledger,
        emergency_ledger=project_budget_ledger,
        emergency_owner_id=PROJECT_BUDGET_OWNER,
    )


def member_cv_service() -> BudgetedCvService:
    reviewer: CvReviewer
    if settings.environment == "production":
        reviewer = GeminiCvReviewer(
            project=settings.gcp_project,
            location=settings.gcp_location,
            model=settings.gemini_model,
        )
    else:
        reviewer = DeterministicCvReviewer()
    return BudgetedCvService(
        reviewer,
        member_budget_ledger,
        emergency_ledger=project_budget_ledger,
        emergency_owner_id=PROJECT_BUDGET_OWNER,
    )


def _budget_payload(ledger: BudgetLedger, owner: str) -> dict[str, int]:
    snapshot = ledger.snapshot(owner)
    return {
        "limit_micro_usd": snapshot.limit_micro_usd,
        "used_micro_usd": snapshot.used_micro_usd,
        "reserved_micro_usd": snapshot.reserved_micro_usd,
        "remaining_micro_usd": snapshot.remaining_micro_usd,
    }


def free_budget() -> dict[str, int]:
    return _budget_payload(free_budget_ledger, "anonymous-free-tier")


def _anonymous_rate_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    peer = request.client.host if request.client else "unknown"
    digest = hashlib.sha256(f"{forwarded}|{peer}".encode()).hexdigest()[:20]
    return f"anonymous:{digest}"


def _enforce_ai_rate(key: str, limit: int, tier: str) -> None:
    try:
        ai_rate_limiter.check(key, limit)
    except RateLimitExceededError:
        emit("security.ai_burst_blocked", access_tier=tier)
        raise


def render(
    request: Request,
    *,
    cv_text: str = "",
    cv_filename: str = "",
    job_text: str = "",
    job_url: str = "",
    error: str = "",
    error_stage: int = 0,
    run_id: str = "",
    assessment: Assessment | None = None,
    ai_review: EvidenceReview | None = None,
    ai_notice: str = "",
    advisor_ids: list[str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    selected_advisor_ids = normalize_advisor_ids(advisor_ids)
    assessment_json = json.dumps(assessment.model_dump(), indent=2) if assessment else ""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "cv_text": cv_text,
            "cv_filename": cv_filename,
            "job_text": job_text,
            "job_url": job_url,
            "error": error,
            "error_stage": error_stage,
            "run_id": run_id,
            "assessment": assessment,
            "assessment_json": assessment_json,
            "ai_review": ai_review,
            "ai_notice": ai_notice,
            "advisors": ADVISORS,
            "advisor_map": ADVISOR_BY_ID,
            "selected_advisor_ids": selected_advisor_ids,
            "selected_advisors": advisor_context(selected_advisor_ids),
            "free_budget": free_budget(),
        },
        status_code=status_code,
    )


@app.get("/api/health")
@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="welcome.html",
        context={
            "auth_mode": settings.auth_mode,
            "google_oauth_client_id": settings.google_oauth_client_id,
        },
    )


@app.get("/tracker", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def tracker(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="tracker.html",
        context={
            "ai_limit_dollars": settings.ai_monthly_limit_micro_usd / 1_000_000,
            "auth_mode": settings.auth_mode,
            "google_oauth_client_id": settings.google_oauth_client_id,
        },
    )


@app.get("/cvs", response_class=HTMLResponse)
def cv_library(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="cvs.html",
        context={
            "auth_mode": settings.auth_mode,
            "google_oauth_client_id": settings.google_oauth_client_id,
        },
    )


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "auth_mode": settings.auth_mode,
            "google_oauth_client_id": settings.google_oauth_client_id,
        },
    )


@app.get("/api/session")
def session(request: Request) -> dict[str, object]:
    user = identity(request)
    record = access_control.status(user)
    return {
        "email": user.email,
        "access": record.status,
        "role": record.role if record.status == "approved" else "none",
    }


@app.post("/api/session/login")
def session_login(payload: SessionCredential) -> JSONResponse:
    user = identity_verifier.verify_token(payload.credential)
    record = access_control.status(user)
    response = JSONResponse(
        {
            "email": user.email,
            "access": record.status,
            "role": record.role if record.status == "approved" else "none",
        }
    )
    response.set_cookie(
        "advisory_session",
        payload.credential,
        max_age=3_600,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )
    return response


@app.post("/api/session/logout", status_code=204)
def session_logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie(
        "advisory_session",
        path="/",
        secure=settings.environment == "production",
        httponly=True,
        samesite="lax",
    )
    return response


@app.post("/api/access-request", status_code=201)
def request_workspace_access(request: Request) -> dict[str, object]:
    user = identity(request)
    record = access_control.request_access(user)
    emit("access.requested", user_id=user.subject, access_id=record.id)
    return record.model_dump(mode="json")


@app.get("/api/admin/access")
def list_workspace_access(request: Request) -> list[dict[str, object]]:
    records = access_control.list_records(identity(request))
    return [record.model_dump(mode="json") for record in records]


@app.post("/api/admin/access", status_code=201)
def approve_workspace_email(request: Request, payload: AccessInvite) -> dict[str, object]:
    record = access_control.approve_email(identity(request), payload.email)
    emit("access.approved", access_id=record.id)
    return record.model_dump(mode="json")


@app.patch("/api/admin/access/{record_id}")
def decide_workspace_access(request: Request, record_id: str, payload: AccessDecision) -> dict[str, object]:
    record = access_control.decide(identity(request), record_id, payload.status)
    emit("access.decided", access_id=record.id, status=record.status)
    return record.model_dump(mode="json")


@app.get("/api/applications")
def list_applications(request: Request) -> list[dict[str, object]]:
    return [item.model_dump(mode="json") for item in career_repository.list_applications(owner_id(request))]


@app.post("/api/applications", status_code=201)
def create_application(request: Request, payload: ApplicationCreate) -> dict[str, object]:
    try:
        item = career_repository.create_application(owner_id(request), payload)
    except NotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    emit("application.created", user_id=owner_id(request), application_id=item.id, status=item.status)
    return item.model_dump(mode="json")


@app.patch("/api/applications/{application_id}")
def update_application(
    request: Request, application_id: str, payload: ApplicationUpdate
) -> dict[str, object]:
    try:
        item = career_repository.update_application(owner_id(request), application_id, payload)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    emit("application.updated", user_id=owner_id(request), application_id=item.id, status=item.status)
    return item.model_dump(mode="json")


@app.get("/api/workspace-archives")
def list_workspace_archives(request: Request) -> list[dict[str, object]]:
    archives = career_repository.list_workspace_archives(owner_id(request))
    return [item.model_dump(mode="json") for item in archives]


@app.post("/api/workspace-archives", status_code=201)
def archive_workspace(request: Request, payload: ArchiveWorkspaceRequest) -> dict[str, object]:
    owner = owner_id(request)
    try:
        archive = career_repository.archive_workspace(owner, payload.label)
    except (EmptyWorkspaceError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    emit(
        "workspace.archived",
        user_id=owner,
        archive_id=archive.id,
        application_count=archive.application_count,
        cv_version_count=archive.cv_version_count,
    )
    return archive.model_dump(mode="json")


@app.get("/api/workspace-archives/{archive_id}")
def get_workspace_archive(request: Request, archive_id: str) -> dict[str, object]:
    owner = owner_id(request)
    try:
        detail = career_repository.get_workspace_archive(owner, archive_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    emit("workspace.archive_viewed", user_id=owner, archive_id=archive_id)
    return {
        "archive": detail.archive.model_dump(mode="json"),
        "applications": [item.model_dump(mode="json") for item in detail.applications],
        "cv_versions": [
            item.model_dump(mode="json", exclude={"extracted_text"})
            for item in detail.cv_versions
        ],
    }


@app.get("/api/workspace-archives/{archive_id}/cv-versions/{cv_version_id}/download")
def download_archived_cv_version(
    request: Request, archive_id: str, cv_version_id: str
) -> Response:
    owner = owner_id(request)
    try:
        detail = career_repository.get_workspace_archive(owner, archive_id)
        version = next(
            item for item in detail.cv_versions if item.id == cv_version_id
        )
        content = career_repository.get_archived_cv_content(owner, archive_id, cv_version_id)
    except (NotFoundError, StopIteration) as exc:
        raise HTTPException(status_code=404, detail="Archived CV version not found") from exc
    return Response(
        content,
        media_type=version.content_type,
        headers={"Content-Disposition": f'attachment; filename="{version.filename}"'},
    )


@app.get("/api/cv-versions")
def list_cv_versions(request: Request) -> list[dict[str, object]]:
    versions = career_repository.list_cv_versions(owner_id(request))
    return [item.model_dump(mode="json", exclude={"extracted_text"}) for item in versions]


@app.get("/api/cv-versions/{cv_version_id}")
def get_cv_version(request: Request, cv_version_id: str) -> dict[str, object]:
    try:
        version = career_repository.get_cv_version(owner_id(request), cv_version_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return version.model_dump(mode="json")


@app.post("/api/cv-versions", status_code=201)
async def create_cv_version(
    request: Request,
    label: str = Form(...),
    cv_file: UploadFile = File(...),  # noqa: B008
) -> dict[str, object]:
    payload = await cv_file.read(settings.max_upload_bytes + 1)
    try:
        item = tracker_service().create_cv_version(
            owner_id(request),
            label=label,
            filename=cv_file.filename or "cv.txt",
            content_type=cv_file.content_type or "application/octet-stream",
            content=payload,
        )
    except (CvDocumentError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    emit("cv_version.created", user_id=owner_id(request), cv_version_id=item.id, file_bytes=item.byte_count)
    return item.model_dump(mode="json", exclude={"extracted_text"})


@app.post("/api/cv-versions/{cv_version_id}/revisions", status_code=201)
def create_cv_revision(
    request: Request,
    cv_version_id: str,
    label: str = Form(...),
    cv_text: str = Form(...),
) -> dict[str, object]:
    owner = owner_id(request)
    try:
        parent = career_repository.get_cv_version(owner, cv_version_id)
        content = cv_text.strip().encode("utf-8")
        item = tracker_service().create_cv_version(
            owner,
            label=label,
            filename=f"{Path(parent.filename).stem}-revised.txt",
            content_type="text/plain",
            content=content,
            parent_version_id=parent.id,
        )
    except (NotFoundError, CvDocumentError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    emit(
        "cv_version.revised",
        user_id=owner,
        cv_version_id=item.id,
        parent_version_id=parent.id,
    )
    return item.model_dump(mode="json", exclude={"extracted_text"})


@app.post("/api/cv-versions/{cv_version_id}/ai-review")
async def standalone_cv_review(request: Request, cv_version_id: str) -> dict[str, object]:
    owner = owner_id(request)
    try:
        version = career_repository.get_cv_version(owner, cv_version_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        _enforce_ai_rate(owner, settings.member_ai_requests_per_minute, "approved")
        review = await run_in_threadpool(member_cv_service().review, owner, version.extracted_text)
    except (BudgetExceededError, RateLimitExceededError) as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return {"review": review.model_dump(), "budget": _budget_payload(member_budget_ledger, owner)}


@app.get("/api/cv-versions/{cv_version_id}/download")
def download_cv_version(request: Request, cv_version_id: str) -> Response:
    try:
        version = career_repository.get_cv_version(owner_id(request), cv_version_id)
        content = career_repository.get_cv_content(owner_id(request), cv_version_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content,
        media_type=version.content_type,
        headers={"Content-Disposition": f'attachment; filename="{version.filename}"'},
    )


@app.get("/api/ai/budget")
def ai_budget(request: Request) -> dict[str, int]:
    return _budget_payload(member_budget_ledger, owner_id(request))


@app.get("/api/free-ai/budget")
def free_ai_budget() -> dict[str, int]:
    return free_budget()


@app.post("/api/applications/{application_id}/ai-review")
async def application_ai_review(
    request: Request, application_id: str, job_text: str = Form("")
) -> dict[str, object]:
    try:
        application = career_repository.get_application(owner_id(request), application_id)
        if not application.cv_version_id:
            raise HTTPException(status_code=422, detail="Attach a CV version before asking AI to review it")
        version = career_repository.get_cv_version(owner_id(request), application.cv_version_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    resolved_job = job_text.strip()
    if not resolved_job and application.job_url:
        try:
            resolved_job = await run_in_threadpool(job_description_fetcher().fetch, application.job_url)
        except JobDescriptionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not resolved_job:
        raise HTTPException(status_code=422, detail="Add a job description or public job link first")
    owner = owner_id(request)
    try:
        _enforce_ai_rate(owner, settings.member_ai_requests_per_minute, "approved")
        review = await run_in_threadpool(
            member_ai_service().review,
            owner,
            version.extracted_text,
            resolved_job,
        )
    except (BudgetExceededError, RateLimitExceededError) as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    career_repository.update_application(
        owner_id(request),
        application_id,
        ApplicationUpdate(fit_score=review.fit_score, ai_summary=review.summary),
    )
    return {"review": review.model_dump(), "budget": _budget_payload(member_budget_ledger, owner)}


@app.get("/workspace", response_class=HTMLResponse)
def workspace(request: Request) -> HTMLResponse:
    return render(request)


@app.post("/demo", response_class=HTMLResponse)
def demo(request: Request) -> HTMLResponse:
    run_id, assessment = service().analyze(DEMO_CV, DEMO_JOB)
    ai_review, _, _ = DeterministicAiReviewer().review(
        DEMO_CV, DEMO_JOB, list(DEFAULT_ADVISOR_IDS)
    )
    return render(
        request,
        cv_text=DEMO_CV,
        job_text=DEMO_JOB,
        run_id=run_id,
        assessment=assessment,
        ai_review=ai_review,
        ai_notice=(
            "This sample demonstrates the report without spending the shared free AI pool. "
            "A real review uses the selected board in one Gemini call."
        ),
        advisor_ids=list(DEFAULT_ADVISOR_IDS),
    )


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(
    request: Request,
    cv_text: str = Form(""),
    cv_file: UploadFile | None = File(None),  # noqa: B008
    job_text: str = Form(""),
    job_url: str = Form(""),
    advisor_ids: str = Form(""),
) -> HTMLResponse:
    selected_advisor_ids = normalize_advisor_ids(advisor_ids.split(","))
    resolved_cv = cv_text.strip()
    cv_filename = ""
    if cv_file and cv_file.filename:
        cv_filename = Path(cv_file.filename).name
        payload = await cv_file.read(settings.max_upload_bytes + 1)
        try:
            resolved_cv = cv_document_parser().parse(cv_filename, payload)
        except CvDocumentError as exc:
            emit(
                "cv.ingestion.failed",
                source="upload",
                file_bytes=len(payload),
                error_type=type(exc).__name__,
            )
            return render(
                request,
                cv_text=cv_text,
                cv_filename=cv_filename,
                job_text=job_text,
                job_url=job_url,
                advisor_ids=selected_advisor_ids,
                error=str(exc),
                error_stage=1,
                status_code=422,
            )
        emit(
            "cv.ingestion.completed",
            source="upload",
            file_bytes=len(payload),
            cv_chars=len(resolved_cv),
        )
    elif resolved_cv:
        emit("cv.ingestion.completed", source="paste", cv_chars=len(resolved_cv))

    if not resolved_cv:
        return render(
            request,
            cv_text=cv_text,
            job_text=job_text,
            job_url=job_url,
            advisor_ids=selected_advisor_ids,
            error="Upload a PDF or TXT CV, or paste the CV text.",
            error_stage=1,
            status_code=422,
        )

    resolved_job = job_text.strip()
    if not resolved_job and job_url.strip():
        try:
            resolved_job = await run_in_threadpool(job_description_fetcher().fetch, job_url)
        except JobDescriptionError as exc:
            emit("job.ingestion.failed", source="url", error_type=type(exc).__name__)
            return render(
                request,
                cv_text=resolved_cv,
                cv_filename=cv_filename,
                job_text=job_text,
                job_url=job_url,
                advisor_ids=selected_advisor_ids,
                error=str(exc),
                error_stage=2,
                status_code=422,
            )
        emit("job.ingestion.completed", source="url", job_chars=len(resolved_job))
    elif resolved_job:
        emit("job.ingestion.completed", source="paste", job_chars=len(resolved_job))

    if not resolved_job:
        return render(
            request,
            cv_text=resolved_cv,
            cv_filename=cv_filename,
            job_text=job_text,
            job_url=job_url,
            advisor_ids=selected_advisor_ids,
            error="Add a public job link or paste the job description.",
            error_stage=2,
            status_code=422,
        )

    try:
        run_id, assessment = service().analyze(resolved_cv, resolved_job)
    except InputError as exc:
        error_stage = 1 if len(resolved_cv) > settings.max_input_chars else 2
        return render(
            request,
            cv_text=resolved_cv,
            cv_filename=cv_filename,
            job_text=resolved_job,
            job_url=job_url,
            advisor_ids=selected_advisor_ids,
            error=str(exc),
            error_stage=error_stage,
            status_code=422,
        )
    ai_review: EvidenceReview | None = None
    ai_notice = ""
    try:
        _enforce_ai_rate(
            _anonymous_rate_key(request), settings.anonymous_ai_requests_per_minute, "anonymous"
        )
        ai_review = await run_in_threadpool(
            free_ai_service().review,
            "anonymous-free-tier",
            resolved_cv,
            resolved_job,
            selected_advisor_ids,
        )
    except BudgetExceededError:
        ai_review, _, _ = DeterministicAiReviewer().review(
            resolved_cv, resolved_job, selected_advisor_ids
        )
        ai_notice = (
            "The shared free AI pool has reached its monthly $5 limit. "
            "The evidence review below still works without a model call."
        )
        emit("gemini.free_pool.exhausted")
    except RateLimitExceededError:
        ai_review, _, _ = DeterministicAiReviewer().review(
            resolved_cv, resolved_job, selected_advisor_ids
        )
        ai_notice = "Free AI is limited to two attempts per minute. The evidence review still completed."
    except Exception as exc:
        ai_review, _, _ = DeterministicAiReviewer().review(
            resolved_cv, resolved_job, selected_advisor_ids
        )
        ai_notice = (
            "Gemini is temporarily unavailable. The evidence review below was completed without a model call."
        )
        emit("gemini.free_pool.fallback", error_type=type(exc).__name__)
    return render(
        request,
        cv_text=resolved_cv,
        cv_filename=cv_filename,
        job_text=resolved_job,
        job_url=job_url,
        run_id=run_id,
        assessment=assessment,
        ai_review=ai_review,
        ai_notice=ai_notice,
        advisor_ids=selected_advisor_ids,
    )


@app.post("/api/assessments")
def api_analyze(cv_text: str = Form(...), job_text: str = Form(...)) -> JSONResponse:
    try:
        run_id, assessment = service().analyze(cv_text, job_text)
    except InputError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse({"run_id": run_id, "assessment": assessment.model_dump()})
