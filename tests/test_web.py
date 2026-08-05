from fastapi.testclient import TestClient

from advisory.web import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_home_explains_product() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Bring a stronger case to your next opportunity" in response.text
    assert 'href="/static/app.css"' in response.text


def test_workspace_starts_guided_review() -> None:
    response = client.get("/workspace")
    assert response.status_code == 200
    assert "Start with your CV" in response.text
    assert 'src="/static/app.js"' in response.text


def test_stylesheet_is_served_as_css() -> None:
    response = client.get("/static/app.css")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    assert "--canvas:#fbfaf8" in response.text


def test_workspace_script_is_served() -> None:
    response = client.get("/static/app.js")
    assert response.status_code == 200
    assert "showStep" in response.text


def test_demo_renders_assessment() -> None:
    response = client.post("/demo")
    assert response.status_code == 200
    assert 'data-testid="results"' in response.text
    assert "commercial ATS" in response.text


def test_api_contract() -> None:
    response = client.post("/api/assessments", data={"cv_text": "EXPERIENCE Python", "job_text": "Python"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["run_id"]) == 32
    assert body["assessment"]["schema_version"] == "1.0"


def test_api_rejects_blank_input() -> None:
    response = client.post("/api/assessments", data={"cv_text": " ", "job_text": "Python"})
    assert response.status_code == 422
