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
    assert "Choose what you need today" in response.text
    assert "Free AI review" in response.text
    assert "Private workspace" in response.text
    assert "Shared $5 monthly AI pool" in response.text
    assert 'href="/static/app.css?v=8"' in response.text


def test_tracker_page_has_board_funnel_and_fast_add() -> None:
    response = client.get("/tracker")
    assert response.status_code == 200
    assert "Application funnel" in response.text
    assert "data-board" in response.text
    assert "data-application-dialog" in response.text
    assert "data-cv-dialog" in response.text
    assert "No in-app cap" in response.text


def test_tracker_api_creates_moves_and_isolates_application() -> None:
    web.career_repository.clear()
    created = client.post(
        "/api/applications",
        headers={"x-advisory-user": "alice"},
        json={"company": "Acme", "role": "AI Engineer", "status": "interested"},
    )
    assert created.status_code == 201
    application_id = created.json()["id"]
    moved = client.patch(
        f"/api/applications/{application_id}",
        headers={"x-advisory-user": "alice"},
        json={"status": "applied"},
    )
    assert moved.json()["status"] == "applied"
    assert len(client.get("/api/applications", headers={"x-advisory-user": "alice"}).json()) == 1
    assert client.get("/api/applications", headers={"x-advisory-user": "bob"}).json() == []
    denied = client.patch(
        f"/api/applications/{application_id}",
        headers={"x-advisory-user": "bob"},
        json={"status": "offer"},
    )
    assert denied.status_code == 404


def test_cv_version_upload_listing_download_and_attachment() -> None:
    web.career_repository.clear()
    headers = {"x-advisory-user": "alice"}
    uploaded = client.post(
        "/api/cv-versions",
        headers=headers,
        data={"label": "AI platform CV"},
        files={"cv_file": ("resume.txt", b"EXPERIENCE\nBuilt Python systems", "text/plain")},
    )
    assert uploaded.status_code == 201
    version = uploaded.json()
    assert "extracted_text" not in version
    assert client.get("/api/cv-versions", headers=headers).json()[0]["label"] == "AI platform CV"
    downloaded = client.get(f"/api/cv-versions/{version['id']}/download", headers=headers)
    assert downloaded.content.startswith(b"EXPERIENCE")
    assert (
        client.get(
            f"/api/cv-versions/{version['id']}/download", headers={"x-advisory-user": "bob"}
        ).status_code
        == 404
    )
    application = client.post(
        "/api/applications",
        headers=headers,
        json={"company": "Acme", "role": "Engineer", "cv_version_id": version["id"]},
    )
    assert application.status_code == 201
    assert application.json()["cv_version_id"] == version["id"]


def test_member_ai_is_unrestricted_and_free_pool_has_hard_limit() -> None:
    payload = client.get("/api/ai/budget", headers={"x-advisory-user": "alice"}).json()
    assert payload == {"unlimited": True}
    free_payload = client.get("/api/free-ai/budget").json()
    assert free_payload["limit_micro_usd"] == 5_000_000
    assert free_payload["remaining_micro_usd"] <= free_payload["limit_micro_usd"]


def test_admin_page_and_development_session() -> None:
    page = client.get("/admin")
    assert page.status_code == 200
    assert "Control who gets in" in page.text
    session = client.get("/api/session").json()
    assert session == {"email": "carlosan.1708@gmail.com", "access": "approved", "role": "admin"}


def test_non_admin_cannot_list_access_records() -> None:
    response = client.get(
        "/api/admin/access",
        headers={"x-advisory-user": "alice", "x-advisory-email": "alice@example.com"},
    )
    assert response.status_code == 403


def test_application_ai_review_requires_cv_and_job_then_persists_summary() -> None:
    web.career_repository.clear()
    headers = {"x-advisory-user": "ai-user"}
    no_cv = client.post(
        "/api/applications",
        headers=headers,
        json={"company": "Acme", "role": "Engineer"},
    ).json()
    assert client.post(f"/api/applications/{no_cv['id']}/ai-review", headers=headers).status_code == 422
    version = client.post(
        "/api/cv-versions",
        headers=headers,
        data={"label": "AI CV"},
        files={"cv_file": ("resume.txt", b"EXPERIENCE\nBuilt Python services", "text/plain")},
    ).json()
    application = client.post(
        "/api/applications",
        headers=headers,
        json={"company": "Acme", "role": "Engineer", "cv_version_id": version["id"]},
    ).json()
    missing_job = client.post(f"/api/applications/{application['id']}/ai-review", headers=headers)
    assert missing_job.status_code == 422
    reviewed = client.post(
        f"/api/applications/{application['id']}/ai-review",
        headers=headers,
        data={"job_text": "Python platform services"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["review"]["fit_score"] > 0
    stored = client.get("/api/applications", headers=headers).json()[0]
    assert stored["ai_summary"]


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
    assert "data-job-fallback open" in response.text


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
