from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from advisory.demo import DEMO_CV, DEMO_JOB
from advisory.domain import Assessment
from advisory.ingestion import (
    CvDocumentError,
    CvDocumentParser,
    JobDescriptionError,
    JobDescriptionFetcher,
)
from advisory.observability import emit
from advisory.service import AssessmentService, InputError
from advisory.settings import get_settings

BASE_DIR = Path(__file__).resolve().parent
settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


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
        },
        status_code=status_code,
    )


@app.get("/api/health")
@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="welcome.html")


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
    return render(
        request,
        cv_text=resolved_cv,
        cv_filename=cv_filename,
        job_text=resolved_job,
        job_url=job_url,
        run_id=run_id,
        assessment=assessment,
    )


@app.post("/api/assessments")
def api_analyze(cv_text: str = Form(...), job_text: str = Form(...)) -> JSONResponse:
    try:
        run_id, assessment = service().analyze(cv_text, job_text)
    except InputError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse({"run_id": run_id, "assessment": assessment.model_dump()})
