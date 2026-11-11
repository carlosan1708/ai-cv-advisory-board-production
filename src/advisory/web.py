from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol, cast

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
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
    AiUsage,
    BudgetedAiService,
    BudgetedCvService,
    CvReview,
    CvReviewer,
    DeterministicAiReviewer,
    DeterministicCvReviewer,
    EvidenceReview,
    MeteredCvReview,
    MeteredEvidenceReview,
    OpenAiCvReviewer,
    OpenAiReviewer,
    OpenAiStructuredClient,
)
from advisory.ai_audit import (
    AiAuditEvent,
    AiAuditRepository,
    AuditReviewType,
    AuditStatus,
    InMemoryAiAuditRepository,
)
from advisory.auth import IdentityVerifier, UserIdentity
from advisory.budget import BudgetExceededError, BudgetLedger, InMemoryBudgetLedger, Pricing
from advisory.career import Application, ApplicationCreate, ApplicationUpdate, SavedBoardReview
from advisory.career_repository import (
    CareerRepository,
    EmptyWorkspaceError,
    InMemoryCareerRepository,
    NotFoundError,
)
from advisory.demo import DEMO_CV, DEMO_JOB
from advisory.domain import Assessment
from advisory.google_persistence import (
    FirestoreAiAuditRepository,
    FirestoreBudgetLedger,
    GoogleCareerRepository,
)
from advisory.ingestion import (
    CvDocumentError,
    CvDocumentParser,
    JobDescriptionError,
    JobDescriptionFetcher,
)
from advisory.interview import (
    MAX_QUESTIONS,
    CvInterviewer,
    DeterministicCvInterviewer,
    InterviewAnswer,
    OpenAiCvInterviewer,
    run_budgeted,
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
    ai_audit_repository: AiAuditRepository = FirestoreAiAuditRepository(settings.gcp_project)
else:
    career_repository = InMemoryCareerRepository()
    free_budget_ledger = InMemoryBudgetLedger(settings.ai_monthly_limit_micro_usd)
    member_budget_ledger = InMemoryBudgetLedger(settings.member_ai_monthly_limit_micro_usd)
    project_budget_ledger = InMemoryBudgetLedger(settings.project_ai_monthly_limit_micro_usd)
    access_control = InMemoryAccessControl(admin_emails, allow_all=settings.auth_mode == "development")
    ai_audit_repository = InMemoryAiAuditRepository()

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


def job_document_parser() -> CvDocumentParser:
    return CvDocumentParser(
        max_file_bytes=settings.max_upload_bytes,
        max_chars=settings.max_input_chars,
        document_name="job description",
    )


APPLICATION_LIST_EXCLUDE = {"job_description", "board_review"}


def application_payload(item: Application) -> dict[str, object]:
    payload = item.model_dump(mode="json", exclude=APPLICATION_LIST_EXCLUDE)
    payload["has_board_review"] = item.board_review is not None
    return payload


def job_description_fetcher() -> JobDescriptionFetcher:
    return JobDescriptionFetcher(
        max_response_bytes=settings.max_job_page_bytes,
        max_chars=settings.max_input_chars,
    )


def tracker_service() -> TrackerService:
    return TrackerService(career_repository, cv_document_parser())


def ai_pricing(*, free_tier: bool = False) -> Pricing:
    if free_tier:
        return Pricing(
            model=settings.free_openai_model,
            version="settings",
            input_micro_usd_per_million=settings.free_openai_input_micro_usd_per_million,
            output_micro_usd_per_million=settings.free_openai_output_micro_usd_per_million,
        )
    return Pricing(
        model=settings.openai_model,
        version="settings",
        input_micro_usd_per_million=settings.openai_input_micro_usd_per_million,
        output_micro_usd_per_million=settings.openai_output_micro_usd_per_million,
    )


@lru_cache(maxsize=2)
def openai_client(model: str) -> OpenAiStructuredClient:
    return OpenAiStructuredClient(
        api_key=settings.openai_api_key.get_secret_value(),
        model=model,
        reasoning_effort=settings.openai_reasoning_effort,
        max_output_tokens=settings.ai_max_output_tokens,
    )


def ai_reviewer(*, free_tier: bool = False) -> AiReviewer:
    if settings.environment == "production":
        model = settings.free_openai_model if free_tier else settings.openai_model
        return OpenAiReviewer(openai_client(model))
    return DeterministicAiReviewer()


def _board_service(ledger: BudgetLedger, *, free_tier: bool = False) -> BudgetedAiService:
    return BudgetedAiService(
        ai_reviewer(free_tier=free_tier),
        ledger,
        pricing=ai_pricing(free_tier=free_tier),
        max_input_tokens=settings.ai_max_input_tokens,
        max_output_tokens=settings.ai_max_output_tokens,
        emergency_ledger=project_budget_ledger,
        emergency_owner_id=PROJECT_BUDGET_OWNER,
    )


def free_ai_service() -> BudgetedAiService:
    return _board_service(free_budget_ledger, free_tier=True)


def member_ai_service() -> BudgetedAiService:
    return _board_service(member_budget_ledger)


def member_cv_service() -> BudgetedCvService:
    reviewer: CvReviewer
    if settings.environment == "production":
        reviewer = OpenAiCvReviewer(openai_client(settings.openai_model))
    else:
        reviewer = DeterministicCvReviewer()
    return BudgetedCvService(
        reviewer,
        member_budget_ledger,
        pricing=ai_pricing(),
        max_input_tokens=settings.ai_max_input_tokens,
        max_output_tokens=settings.ai_max_output_tokens,
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


def _record_ai_audit(event: AiAuditEvent) -> None:
    try:
        ai_audit_repository.record(event)
    except Exception as exc:
        emit("ai.audit.write_failed", error_type=type(exc).__name__)


class _BasicBoardService(Protocol):
    def review(
        self,
        owner: str,
        cv_text: str,
        job_text: str,
        advisor_ids: list[str] | None = None,
    ) -> EvidenceReview: ...


class _BasicCvService(Protocol):
    def review(self, owner: str, cv_text: str) -> CvReview: ...


def _board_review_with_usage(
    review_service: object,
    owner: str,
    cv_text: str,
    job_text: str,
    advisor_ids: list[str] | None = None,
) -> tuple[EvidenceReview, AiUsage | None]:
    detailed_review = getattr(review_service, "review_with_usage", None)
    if callable(detailed_review):
        result = detailed_review(owner, cv_text, job_text, advisor_ids)
        if isinstance(result, MeteredEvidenceReview):
            return result.review, result.usage
    return cast(_BasicBoardService, review_service).review(
        owner, cv_text, job_text, advisor_ids
    ), None


def _cv_review_with_usage(
    review_service: object, owner: str, cv_text: str
) -> tuple[CvReview, AiUsage | None]:
    detailed_review = getattr(review_service, "review_with_usage", None)
    if callable(detailed_review):
        result = detailed_review(owner, cv_text)
        if isinstance(result, MeteredCvReview):
            return result.review, result.usage
    return cast(_BasicCvService, review_service).review(owner, cv_text), None


def _score_band(score: int) -> str:
    return "strong" if score >= 75 else "partial" if score >= 45 else "weak"


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
    ai_degraded: bool = False,
    advisor_ids: list[str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    selected_advisor_ids = normalize_advisor_ids(
        list(DEFAULT_ADVISOR_IDS) if advisor_ids is None else advisor_ids
    )
    assessment_json = json.dumps(assessment.model_dump(), indent=2) if assessment else ""
    use_panel_score = ai_review is not None and not ai_degraded and not ai_notice
    headline_score = (
        ai_review.fit_score if use_panel_score and ai_review else assessment.score if assessment else 0
    )
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
            "headline_score": headline_score,
            "headline_band": _score_band(headline_score),
            "headline_source": "panel" if use_panel_score else "evidence",
            "ai_review": ai_review,
            "ai_notice": ai_notice,
            "ai_degraded": ai_degraded,
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
            "ai_model": settings.openai_model,
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


@app.get("/api/admin/usage")
def admin_ai_usage(request: Request) -> dict[str, object]:
    admin_user = identity(request)
    access_control.require_admin(admin_user)
    access_records = access_control.list_records(admin_user)
    owner_labels = {record.subject: record.email for record in access_records if record.subject}
    owner_labels[admin_user.subject] = admin_user.email

    members: list[dict[str, object]] = []
    seen_subjects: set[str] = set()
    approved_identities = [
        (record.subject, record.email)
        for record in access_records
        if record.status == "approved" and record.subject
    ]
    approved_identities.append((admin_user.subject, admin_user.email))
    for subject, email in approved_identities:
        if subject in seen_subjects:
            continue
        seen_subjects.add(subject)
        members.append({"email": email, **_budget_payload(member_budget_ledger, subject)})

    events = ai_audit_repository.list_recent(100)
    event_payloads: list[dict[str, object]] = []
    for event in events:
        payload = event.model_dump(mode="json", exclude={"owner_id"})
        payload["owner_label"] = (
            "Anonymous free review"
            if event.access_tier == "anonymous"
            else owner_labels.get(event.owner_id, "Approved member")
        )
        event_payloads.append(payload)

    now = datetime.now(UTC)
    current_month = now.strftime("%Y-%m")
    reviews_this_month = ai_audit_repository.count_since(
        datetime(now.year, now.month, 1, tzinfo=UTC)
    )
    return {
        "month": current_month,
        "model": f"{settings.openai_model} (members) · {settings.free_openai_model} (free)",
        "privacy_note": "Operational metadata only. CV text, job text, and generated prose are not stored.",
        "free": _budget_payload(free_budget_ledger, "anonymous-free-tier"),
        "project": _budget_payload(project_budget_ledger, PROJECT_BUDGET_OWNER),
        "members": members,
        "member_used_micro_usd": sum(
            cast(int, member["used_micro_usd"]) for member in members
        ),
        "reviews_this_month": reviews_this_month,
        "recent_reviews": event_payloads,
    }


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
    return [
        application_payload(item)
        for item in career_repository.list_applications(owner_id(request))
    ]


@app.post("/api/applications", status_code=201)
def create_application(request: Request, payload: ApplicationCreate) -> dict[str, object]:
    try:
        item = career_repository.create_application(owner_id(request), payload)
    except NotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    emit("application.created", user_id=owner_id(request), application_id=item.id, status=item.status)
    return application_payload(item)


@app.patch("/api/applications/{application_id}")
def update_application(
    request: Request, application_id: str, payload: ApplicationUpdate
) -> dict[str, object]:
    try:
        item = career_repository.update_application(owner_id(request), application_id, payload)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    emit("application.updated", user_id=owner_id(request), application_id=item.id, status=item.status)
    return application_payload(item)


@app.post("/api/applications/{application_id}/job-description")
async def upload_job_description(
    request: Request,
    application_id: str,
    job_file: UploadFile = File(...),  # noqa: B008
) -> dict[str, object]:
    owner = owner_id(request)
    filename = Path(job_file.filename or "job-description.txt").name[:200]
    payload = await job_file.read(settings.max_upload_bytes + 1)
    try:
        career_repository.get_application(owner, application_id)
        text = job_document_parser().parse(filename, payload)
        item = career_repository.update_application(
            owner,
            application_id,
            ApplicationUpdate(job_description=text, job_description_filename=filename),
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CvDocumentError as exc:
        emit("job.ingestion.failed", source="upload", file_bytes=len(payload), error_type=type(exc).__name__)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    emit("job.ingestion.completed", source="upload", file_bytes=len(payload), job_chars=len(text))
    return application_payload(item)


@app.delete("/api/applications/{application_id}/job-description")
def remove_job_description(request: Request, application_id: str) -> dict[str, object]:
    owner = owner_id(request)
    try:
        item = career_repository.update_application(
            owner,
            application_id,
            ApplicationUpdate(job_description="", job_description_filename=""),
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return application_payload(item)


@app.delete("/api/applications/{application_id}", status_code=204)
def delete_application(request: Request, application_id: str) -> Response:
    owner = owner_id(request)
    try:
        career_repository.delete_application(owner, application_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    emit("application.deleted", user_id=owner, application_id=application_id)
    return Response(status_code=204)


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
        "applications": [
            application_payload(item) for item in detail.applications
        ],
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
        review, usage = await run_in_threadpool(
            _cv_review_with_usage, member_cv_service(), owner, version.extracted_text
        )
    except BudgetExceededError as exc:
        _record_ai_audit(
            AiAuditEvent.new(
                owner_id=owner,
                access_tier="approved",
                review_type="cv",
                status="budget_limited",
                model=settings.openai_model,
            )
        )
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RateLimitExceededError as exc:
        _record_ai_audit(
            AiAuditEvent.new(
                owner_id=owner,
                access_tier="approved",
                review_type="cv",
                status="rate_limited",
                model=settings.openai_model,
            )
        )
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception:
        _record_ai_audit(
            AiAuditEvent.new(
                owner_id=owner,
                access_tier="approved",
                review_type="cv",
                status="provider_error",
                model=settings.openai_model,
            )
        )
        raise
    _record_ai_audit(
        AiAuditEvent.new(
            owner_id=owner,
            access_tier="approved",
            review_type="cv",
            status="ai",
            score=review.quality_score,
            band=_score_band(review.quality_score),
            model=usage.model if usage else settings.openai_model,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            actual_micro_usd=usage.actual_micro_usd if usage else 0,
            duration_ms=usage.duration_ms if usage else 0,
        )
    )
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
    resolved_job = job_text.strip() or application.job_description.strip()
    if not resolved_job and application.job_url:
        try:
            resolved_job = await run_in_threadpool(job_description_fetcher().fetch, application.job_url)
        except JobDescriptionError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"{exc} You can also upload the posting as a PDF on the application.",
            ) from exc
    if not resolved_job:
        raise HTTPException(
            status_code=422,
            detail="Add a public job link, upload the job description PDF, or paste the description first",
        )
    owner = owner_id(request)
    try:
        _enforce_ai_rate(owner, settings.member_ai_requests_per_minute, "approved")
        review, usage = await run_in_threadpool(
            _board_review_with_usage,
            member_ai_service(),
            owner,
            version.extracted_text,
            resolved_job,
        )
    except BudgetExceededError as exc:
        _record_ai_audit(
            AiAuditEvent.new(
                owner_id=owner,
                access_tier="approved",
                review_type="application",
                status="budget_limited",
                model=settings.openai_model,
            )
        )
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RateLimitExceededError as exc:
        _record_ai_audit(
            AiAuditEvent.new(
                owner_id=owner,
                access_tier="approved",
                review_type="application",
                status="rate_limited",
                model=settings.openai_model,
            )
        )
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception:
        _record_ai_audit(
            AiAuditEvent.new(
                owner_id=owner,
                access_tier="approved",
                review_type="application",
                status="provider_error",
                model=settings.openai_model,
            )
        )
        raise
    _record_ai_audit(
        AiAuditEvent.new(
            owner_id=owner,
            access_tier="approved",
            review_type="application",
            status="ai",
            score=review.fit_score,
            band=_score_band(review.fit_score),
            model=usage.model if usage else settings.openai_model,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            actual_micro_usd=usage.actual_micro_usd if usage else 0,
            duration_ms=usage.duration_ms if usage else 0,
        )
    )
    career_repository.update_application(
        owner_id(request),
        application_id,
        ApplicationUpdate(fit_score=review.fit_score, ai_summary=review.summary),
    )
    return {"review": review.model_dump(), "budget": _budget_payload(member_budget_ledger, owner)}


@app.get("/workspace", response_class=HTMLResponse)
def workspace(request: Request) -> HTMLResponse:
    return render(request)


@app.get("/review", response_class=HTMLResponse)
def guided_review_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context={
            "auth_mode": settings.auth_mode,
            "google_oauth_client_id": settings.google_oauth_client_id,
            "advisors": ADVISORS,
            "default_advisor_ids": list(DEFAULT_ADVISOR_IDS),
            "advisors_data": [asdict(advisor) for advisor in ADVISORS],
        },
    )


def cv_interviewer() -> CvInterviewer:
    if settings.environment == "production":
        return OpenAiCvInterviewer(
            openai_client(settings.openai_model),
            draft_output_tokens=settings.ai_max_draft_output_tokens,
        )
    return DeterministicCvInterviewer()


def _audit_member(
    review_type: AuditReviewType, owner: str, status: AuditStatus, usage: AiUsage | None
) -> None:
    _record_ai_audit(
        AiAuditEvent.new(
            owner_id=owner,
            access_tier="approved",
            review_type=review_type,
            status=status,
            model=usage.model if usage else settings.openai_model,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            actual_micro_usd=usage.actual_micro_usd if usage else 0,
            duration_ms=usage.duration_ms if usage else 0,
        )
    )


FALLBACK_NOTICES = {
    "budget_limited": "Your monthly AI allowance is used up, so this was prepared without an AI model.",
    "rate_limited": "Too many AI requests in the last minute, so this was prepared without an AI model. "
    "Try again shortly for the AI version.",
    "fallback": "The AI model is temporarily unavailable, so this was prepared without it.",
}


async def _member_ai(
    owner: str,
    review_type: AuditReviewType,
    max_output_tokens: int,
    call: Callable[[], tuple[Any, int, int]],
    fallback: Callable[[], tuple[Any, int, int]],
) -> tuple[Any, str]:
    """Run a budgeted member AI call; on any limit or provider failure use the rule-based fallback."""
    status: AuditStatus = "ai"
    usage: AiUsage | None = None
    try:
        _enforce_ai_rate(owner, settings.member_ai_requests_per_minute, "approved")
        result, usage = await run_in_threadpool(
            run_budgeted,
            ledger=member_budget_ledger,
            owner_id=owner,
            pricing=ai_pricing(),
            max_input_tokens=settings.ai_max_input_tokens,
            max_output_tokens=max_output_tokens,
            call=call,
            event=f"ai.{review_type}",
            emergency_ledger=project_budget_ledger,
            emergency_owner_id=PROJECT_BUDGET_OWNER,
        )
    except BudgetExceededError:
        status = "budget_limited"
    except RateLimitExceededError:
        status = "rate_limited"
    except Exception as exc:
        status = "fallback"
        emit("ai.member.fallback", review_type=review_type, error_type=type(exc).__name__)
    _audit_member(review_type, owner, status, usage)
    if status != "ai":
        result, _, _ = fallback()
        return result, FALLBACK_NOTICES[status]
    return result, ""


@app.post("/api/applications/{application_id}/board-review")
async def application_board_review(
    request: Request,
    application_id: str,
    advisor_ids: str = Form(""),
    job_text: str = Form(""),
) -> dict[str, object]:
    owner = owner_id(request)
    selected = normalize_advisor_ids(advisor_ids.split(","))
    if not selected:
        raise HTTPException(status_code=422, detail="Choose at least one specialist for your board.")
    try:
        application = career_repository.get_application(owner, application_id)
        if not application.cv_version_id:
            raise HTTPException(status_code=422, detail="Choose a CV for this application first.")
        version = career_repository.get_cv_version(owner, application.cv_version_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    pasted = job_text.strip()
    resolved_job = pasted or application.job_description.strip()
    if not resolved_job and application.job_url:
        try:
            resolved_job = await run_in_threadpool(job_description_fetcher().fetch, application.job_url)
        except JobDescriptionError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"{exc} Upload the posting as a PDF or paste the description instead.",
            ) from exc
    if not resolved_job:
        raise HTTPException(
            status_code=422,
            detail="Add a public job link, upload the job description PDF, or paste the description.",
        )
    try:
        _, assessment = service().analyze(version.extracted_text, resolved_job)
    except InputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    status: AuditStatus = "ai"
    usage: AiUsage | None = None
    try:
        _enforce_ai_rate(owner, settings.member_ai_requests_per_minute, "approved")
        review, usage = await run_in_threadpool(
            _board_review_with_usage,
            member_ai_service(),
            owner,
            version.extracted_text,
            resolved_job,
            selected,
        )
    except BudgetExceededError:
        status = "budget_limited"
    except RateLimitExceededError:
        status = "rate_limited"
    except Exception as exc:
        status = "fallback"
        emit("ai.member.fallback", review_type="application", error_type=type(exc).__name__)
    if status != "ai":
        review, _, _ = DeterministicAiReviewer().review(version.extracted_text, resolved_job, selected)
    _audit_member("application", owner, status, usage)

    saved = SavedBoardReview(
        created_at=datetime.now(UTC),
        model=usage.model if usage else "rule-based",
        degraded=status != "ai",
        notice=FALLBACK_NOTICES.get(status, ""),
        cv_version_id=version.id,
        advisor_ids=selected,
        review=review.model_dump(mode="json"),
        assessment=assessment.model_dump(mode="json"),
    )
    update = ApplicationUpdate(board_review=saved, fit_score=review.fit_score, ai_summary=review.summary)
    if pasted and not application.job_description:
        update.job_description = pasted[:30_000]
        update.job_description_filename = "Pasted description"
    item = career_repository.update_application(owner, application_id, update)
    emit("application.board_review_saved", user_id=owner, application_id=item.id, degraded=saved.degraded)
    return {
        "application": application_payload(item),
        "board_review": saved.model_dump(mode="json"),
        "budget": _budget_payload(member_budget_ledger, owner),
    }


@app.get("/api/applications/{application_id}/board-review")
def get_application_board_review(request: Request, application_id: str) -> dict[str, object]:
    try:
        item = career_repository.get_application(owner_id(request), application_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if item.board_review is None:
        raise HTTPException(status_code=404, detail="No saved report for this application yet.")
    return {
        "application": application_payload(item),
        "board_review": item.board_review.model_dump(mode="json"),
    }


class InterviewDraftRequest(BaseModel):
    application_id: str | None = Field(default=None, max_length=64)
    answers: list[InterviewAnswer] = Field(max_length=MAX_QUESTIONS)


def _interview_context(owner: str, application_id: str | None) -> str:
    if not application_id:
        return ""
    try:
        application = career_repository.get_application(owner, application_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if application.job_description.strip():
        return application.job_description
    target = f"Target role: {application.role} at {application.company}."
    if application.board_review is not None:
        gaps = [str(item) for item in application.board_review.review.get("evidence_gaps", [])]
        if gaps:
            return f"{target} Gaps found in the last review: {', '.join(gaps)}."
    return target


def _cv_text(owner: str, cv_version_id: str) -> str:
    try:
        return career_repository.get_cv_version(owner, cv_version_id).extracted_text
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/cv-versions/{cv_version_id}/interview")
async def cv_interview_questions(
    request: Request, cv_version_id: str, application_id: str = Form("")
) -> dict[str, object]:
    owner = owner_id(request)
    cv_text = _cv_text(owner, cv_version_id)
    job_text = _interview_context(owner, application_id or None)
    interviewer = cv_interviewer()
    result, notice = await _member_ai(
        owner,
        "cv_interview",
        settings.ai_max_output_tokens,
        lambda: interviewer.questions(cv_text, job_text),
        lambda: DeterministicCvInterviewer().questions(cv_text, job_text),
    )
    return {"questions": result.model_dump(mode="json")["questions"], "notice": notice}


@app.post("/api/cv-versions/{cv_version_id}/interview/draft")
async def cv_interview_draft(
    request: Request, cv_version_id: str, payload: InterviewDraftRequest
) -> dict[str, object]:
    owner = owner_id(request)
    if not any(item.answer.strip() for item in payload.answers):
        raise HTTPException(status_code=422, detail="Answer at least one question first.")
    cv_text = _cv_text(owner, cv_version_id)
    job_text = _interview_context(owner, payload.application_id)
    interviewer = cv_interviewer()
    result, notice = await _member_ai(
        owner,
        "cv_draft",
        settings.ai_max_draft_output_tokens,
        lambda: interviewer.draft(cv_text, job_text, payload.answers),
        lambda: DeterministicCvInterviewer().draft(cv_text, job_text, payload.answers),
    )
    return {"draft": result.model_dump(mode="json"), "notice": notice}


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
            "A real review sends your selected board to the AI model in one call."
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

    if not selected_advisor_ids:
        return render(
            request,
            cv_text=resolved_cv,
            cv_filename=cv_filename,
            job_text=resolved_job,
            job_url=job_url,
            advisor_ids=[],
            error="Choose at least one specialist for your advisory board.",
            error_stage=3,
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
    ai_degraded = False
    audit_status: AuditStatus = "ai"
    usage: AiUsage | None = None
    try:
        _enforce_ai_rate(
            _anonymous_rate_key(request), settings.anonymous_ai_requests_per_minute, "anonymous"
        )
        ai_review, usage = await run_in_threadpool(
            _board_review_with_usage,
            free_ai_service(),
            "anonymous-free-tier",
            resolved_cv,
            resolved_job,
            selected_advisor_ids,
        )
    except BudgetExceededError:
        audit_status = "budget_limited"
        ai_degraded = True
        ai_review, _, _ = DeterministicAiReviewer().review(
            resolved_cv, resolved_job, selected_advisor_ids
        )
        ai_notice = (
            "The shared free AI pool has reached its monthly $5 limit. "
            "The evidence review below still works without a model call."
        )
        emit("ai.free_pool.exhausted")
    except RateLimitExceededError:
        audit_status = "rate_limited"
        ai_degraded = True
        ai_review, _, _ = DeterministicAiReviewer().review(
            resolved_cv, resolved_job, selected_advisor_ids
        )
        ai_notice = "Free AI is limited to two attempts per minute. The evidence review still completed."
    except Exception as exc:
        audit_status = "fallback"
        ai_degraded = True
        ai_review, _, _ = DeterministicAiReviewer().review(
            resolved_cv, resolved_job, selected_advisor_ids
        )
        ai_notice = (
            "The AI model is temporarily unavailable. The review below was completed without a model call."
        )
        emit("ai.free_pool.fallback", error_type=type(exc).__name__)
    _record_ai_audit(
        AiAuditEvent.new(
            owner_id="anonymous-free-tier",
            access_tier="anonymous",
            review_type="job_match",
            status=audit_status,
            advisor_ids=selected_advisor_ids,
            score=ai_review.fit_score if ai_review and not ai_degraded else assessment.score,
            band=_score_band(ai_review.fit_score) if ai_review and not ai_degraded else assessment.band,
            model=usage.model if usage else settings.free_openai_model,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            actual_micro_usd=usage.actual_micro_usd if usage else 0,
            duration_ms=usage.duration_ms if usage else 0,
        )
    )
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
        ai_degraded=ai_degraded,
        advisor_ids=selected_advisor_ids,
    )


@app.post("/api/assessments")
def api_analyze(cv_text: str = Form(...), job_text: str = Form(...)) -> JSONResponse:
    try:
        run_id, assessment = service().analyze(cv_text, job_text)
    except InputError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse({"run_id": run_id, "assessment": assessment.model_dump()})
