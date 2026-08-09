from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from advisory.access import (
    AccessControl,
    AccessDecision,
    AccessInvite,
    FirestoreAccessControl,
    InMemoryAccessControl,
)
from advisory.ai import (
    AiReviewer,
    BudgetedAiService,
    DeterministicAiReviewer,
    EvidenceReview,
    GeminiAiReviewer,
    UnrestrictedAiService,
)
from advisory.auth import IdentityVerifier, UserIdentity
from advisory.budget import BudgetExceededError, BudgetLedger, InMemoryBudgetLedger
from advisory.career import ApplicationCreate, ApplicationUpdate
from advisory.career_repository import CareerRepository, InMemoryCareerRepository, NotFoundError
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
from advisory.service import AssessmentService, InputError
from advisory.settings import get_settings
from advisory.tracker_service import TrackerService

BASE_DIR = Path(__file__).resolve().parent
settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
identity_verifier = IdentityVerifier(settings.auth_mode, settings.google_oauth_client_id)
admin_emails = {email.strip().casefold() for email in settings.admin_emails.split(",") if email.strip()}
if settings.repository_backend == "firestore":
    career_repository: CareerRepository = GoogleCareerRepository(settings.gcp_project, settings.cv_bucket)
    free_budget_ledger: BudgetLedger = FirestoreBudgetLedger(
        settings.gcp_project, settings.ai_monthly_limit_micro_usd
    )
    access_control: AccessControl = FirestoreAccessControl(settings.gcp_project, admin_emails)
else:
    career_repository = InMemoryCareerRepository()
    free_budget_ledger = InMemoryBudgetLedger(settings.ai_monthly_limit_micro_usd)
    access_control = InMemoryAccessControl(admin_emails, allow_all=settings.auth_mode == "development")


def owner_id(request: Request) -> str:
    identity = identity_verifier.verify(request)
    access_control.require_access(identity)
    return identity.subject


def identity(request: Request) -> UserIdentity:
    return identity_verifier.verify(request)


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
    return BudgetedAiService(ai_reviewer(), free_budget_ledger)


def member_ai_service() -> UnrestrictedAiService:
    return UnrestrictedAiService(ai_reviewer())


def free_budget() -> dict[str, int]:
    snapshot = free_budget_ledger.snapshot("anonymous-free-tier")
    return {
        "limit_micro_usd": snapshot.limit_micro_usd,
        "used_micro_usd": snapshot.used_micro_usd,
        "reserved_micro_usd": snapshot.reserved_micro_usd,
        "remaining_micro_usd": snapshot.remaining_micro_usd,
    }


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
    status_code: int = 200,
) -> HTMLResponse:
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


@app.get("/api/cv-versions")
def list_cv_versions(request: Request) -> list[dict[str, object]]:
    versions = career_repository.list_cv_versions(owner_id(request))
    return [item.model_dump(mode="json", exclude={"extracted_text"}) for item in versions]


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
def ai_budget(request: Request) -> dict[str, bool]:
    owner_id(request)
    return {"unlimited": True}


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
    review = await run_in_threadpool(
        member_ai_service().review,
        owner_id(request),
        version.extracted_text,
        resolved_job,
    )
    career_repository.update_application(
        owner_id(request),
        application_id,
        ApplicationUpdate(fit_score=review.fit_score, ai_summary=review.summary),
    )
    return {"review": review.model_dump(), "unlimited": True}


@app.get("/workspace", response_class=HTMLResponse)
def workspace(request: Request) -> HTMLResponse:
    return render(request)


@app.post("/demo", response_class=HTMLResponse)
def demo(request: Request) -> HTMLResponse:
    run_id, assessment = service().analyze(DEMO_CV, DEMO_JOB)
    return render(request, cv_text=DEMO_CV, job_text=DEMO_JOB, run_id=run_id, assessment=assessment)


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(
    request: Request,
    cv_text: str = Form(""),
    cv_file: UploadFile | None = File(None),  # noqa: B008
    job_text: str = Form(""),
    job_url: str = Form(""),
) -> HTMLResponse:
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
            error=str(exc),
            error_stage=error_stage,
            status_code=422,
        )
    ai_review: EvidenceReview | None = None
    ai_notice = ""
    try:
        ai_review = await run_in_threadpool(
            free_ai_service().review,
            "anonymous-free-tier",
            resolved_cv,
            resolved_job,
        )
    except BudgetExceededError:
        ai_notice = (
            "The shared free AI pool has reached its monthly $5 limit. "
            "The evidence review below still works without a model call."
        )
        emit("gemini.free_pool.exhausted")
    except Exception as exc:
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
    )


@app.post("/api/assessments")
def api_analyze(cv_text: str = Form(...), job_text: str = Form(...)) -> JSONResponse:
    try:
        run_id, assessment = service().analyze(cv_text, job_text)
    except InputError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse({"run_id": run_id, "assessment": assessment.model_dump()})
