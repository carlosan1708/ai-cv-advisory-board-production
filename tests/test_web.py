import pytest
from fastapi.testclient import TestClient

from advisory import web
from advisory.ingestion import JobDescriptionError
from advisory.web import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/api/health").json() == {"status": "ok"}


def test_home_explains_product_and_board() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Put your CV in front of the board" in response.text
    assert "Upload your CV" in response.text
    assert "Add the job link" in response.text
    assert 'href="/static/app.css?v=6"' in response.text


def test_workspace_starts_three_stage_review() -> None:
    response = client.get("/workspace")
    assert response.status_code == 200
    assert "Upload the CV you want reviewed" in response.text
    assert 'type="file"' in response.text
    assert "Public job link" in response.text
    assert "Paste CV text instead" in response.text
    assert "CV" in response.text
    assert "Job" in response.text
    assert "Findings" in response.text
    assert 'src="/static/app.js?v=6"' in response.text
    assert 'enctype="multipart/form-data"' in response.text


def test_stylesheet_is_served_as_css() -> None:
    response = client.get("/static/app.css")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    assert "--canvas: #f7f7f4" in response.text
    assert "--brand: #176b5b" in response.text
    assert "--plum" not in response.text


def test_workspace_script_includes_guidance_and_export() -> None:
    response = client.get("/static/app.js")
    assert response.status_code == 200
    assert "showStep" in response.text
    assert "maximumFileSize" in response.text
    assert "validateTarget" in response.text
    assert "data-char-count" in response.text
    assert "data-download-json" in response.text


def test_demo_renders_complete_board_finding() -> None:
    response = client.post("/demo")
    assert response.status_code == 200
    assert 'data-testid="results"' in response.text
    assert "Advisor lenses" in response.text
    assert "Requirement by requirement" in response.text
    assert "commercial ATS" in response.text
    assert 'data-testid="download-json-button"' in response.text


def test_result_wording_changes_for_weak_match() -> None:
    response = client.post(
        "/analyze",
        data={
            "cv_text": "EXPERIENCE\nMaintained internal documentation",
            "job_text": "Kubernetes Terraform Python distributed systems leadership",
        },
    )
    assert response.status_code == 200
    assert "asks for evidence the CV does not yet show" in response.text


def test_uploaded_cv_and_job_url_complete_review(monkeypatch: pytest.MonkeyPatch) -> None:
    requested_urls: list[str] = []

    class FakeFetcher:
        def fetch(self, url: str) -> str:
            requested_urls.append(url)
            return "Python Kubernetes platform leadership"

    monkeypatch.setattr(web, "job_description_fetcher", lambda: FakeFetcher())
    response = client.post(
        "/analyze",
        data={"job_url": "https://jobs.example/platform-engineer"},
        files={
            "cv_file": (
                "Carlos-resume.txt",
                b"EXPERIENCE\nBuilt Python platforms\nSKILLS\nPython\nEDUCATION\nComputer Science",
                "text/plain",
            )
        },
    )
    assert response.status_code == 200
    assert 'data-testid="results"' in response.text
    assert requested_urls == ["https://jobs.example/platform-engineer"]


def test_manual_job_description_takes_precedence_over_url(monkeypatch: pytest.MonkeyPatch) -> None:
    class UnexpectedFetcher:
        def fetch(self, _: str) -> str:
            raise AssertionError("URL must not be fetched when manual text is present")

    monkeypatch.setattr(web, "job_description_fetcher", lambda: UnexpectedFetcher())
    response = client.post(
        "/analyze",
        data={
            "cv_text": "EXPERIENCE\nBuilt Python services",
            "job_url": "https://jobs.example/role",
            "job_text": "Python backend engineering",
        },
    )
    assert response.status_code == 200
    assert 'data-testid="results"' in response.text


def test_bad_upload_returns_to_cv_stage() -> None:
    response = client.post(
        "/analyze",
        data={"job_url": "https://jobs.example/role"},
        files={"cv_file": ("resume.docx", b"not supported", "application/octet-stream")},
    )
    assert response.status_code == 422
    assert "That file type is not supported" in response.text
    assert 'class="review-panel visible" data-step-panel="1"' in response.text
    assert 'class="review-panel " data-step-panel="2"' in response.text
    assert "Upload the CV you want reviewed" in response.text


def test_job_url_error_preserves_cv_and_opens_manual_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    class BlockedFetcher:
        def fetch(self, _: str) -> str:
            raise JobDescriptionError("The job site blocked the request. Paste the description instead.")

    monkeypatch.setattr(web, "job_description_fetcher", lambda: BlockedFetcher())
    response = client.post(
        "/analyze",
        data={"job_url": "https://jobs.example/blocked"},
        files={
            "cv_file": (
                "resume.txt",
                b"EXPERIENCE\nBuilt <platform> systems",
                "text/plain",
            )
        },
    )
    assert response.status_code == 422
    assert "Paste the description instead" in response.text
    assert "CV ready" in response.text
    assert "resume.txt" in response.text
    assert "Built &lt;platform&gt; systems" in response.text
    assert 'data-job-fallback open' in response.text


def test_user_evidence_is_html_escaped() -> None:
    response = client.post(
        "/analyze",
        data={"cv_text": "EXPERIENCE\n<script>alert(1)</script>", "job_text": "script"},
    )
    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text


def test_api_contract() -> None:
    response = client.post("/api/assessments", data={"cv_text": "EXPERIENCE Python", "job_text": "Python"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["run_id"]) == 32
    assert body["assessment"]["schema_version"] == "1.0"


def test_api_rejects_blank_input() -> None:
    response = client.post("/api/assessments", data={"cv_text": " ", "job_text": "Python"})
    assert response.status_code == 422
