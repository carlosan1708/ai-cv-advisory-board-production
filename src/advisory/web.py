from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from advisory.demo import DEMO_CV, DEMO_JOB
from advisory.domain import Assessment
from advisory.service import AssessmentService, InputError
from advisory.settings import get_settings

BASE_DIR = Path(__file__).resolve().parent
settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def service() -> AssessmentService:
    return AssessmentService(max_input_chars=settings.max_input_chars)


def render(
    request: Request,
    *,
    cv_text: str = "",
    job_text: str = "",
    error: str = "",
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
            "job_text": job_text,
            "error": error,
            "run_id": run_id,
            "assessment": assessment,
            "assessment_json": assessment_json,
        },
        status_code=status_code,
    )


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return render(request)


@app.post("/demo", response_class=HTMLResponse)
def demo(request: Request) -> HTMLResponse:
    run_id, assessment = service().analyze(DEMO_CV, DEMO_JOB)
    return render(request, cv_text=DEMO_CV, job_text=DEMO_JOB, run_id=run_id, assessment=assessment)


@app.post("/analyze", response_class=HTMLResponse)
def analyze(request: Request, cv_text: str = Form(...), job_text: str = Form(...)) -> HTMLResponse:
    try:
        run_id, assessment = service().analyze(cv_text, job_text)
    except InputError as exc:
        return render(request, cv_text=cv_text, job_text=job_text, error=str(exc), status_code=422)
    return render(request, cv_text=cv_text, job_text=job_text, run_id=run_id, assessment=assessment)


@app.post("/api/assessments")
def api_analyze(cv_text: str = Form(...), job_text: str = Form(...)) -> JSONResponse:
    try:
        run_id, assessment = service().analyze(cv_text, job_text)
    except InputError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse({"run_id": run_id, "assessment": assessment.model_dump()})
