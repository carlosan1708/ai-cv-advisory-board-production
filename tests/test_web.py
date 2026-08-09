from fastapi.testclient import TestClient

from advisory.web import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/api/health").json() == {"status": "ok"}


def test_home_explains_product_and_board() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Your CV should make its case before you enter the interview" in response.text
    assert "Technical Recruiter" in response.text
    assert "Evidence ledger" in response.text
    assert 'href="/static/app.css?v=5"' in response.text


def test_workspace_starts_three_stage_review() -> None:
    response = client.get("/workspace")
    assert response.status_code == 200
    assert "Add the evidence you want challenged" in response.text
    assert "Evidence" in response.text
    assert "Target" in response.text
    assert "Findings" in response.text
    assert 'src="/static/app.js?v=5"' in response.text


def test_stylesheet_is_served_as_css() -> None:
    response = client.get("/static/app.css")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    assert "--canvas: #f7f8fa" in response.text
    assert "--brand: #2855f5" in response.text
    assert "--plum" not in response.text


def test_workspace_script_includes_guidance_and_export() -> None:
    response = client.get("/static/app.js")
    assert response.status_code == 200
    assert "showStep" in response.text
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
