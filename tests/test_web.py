from fastapi.testclient import TestClient

from advisory.web import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_home_explains_product() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Know what your CV proves" in response.text


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

