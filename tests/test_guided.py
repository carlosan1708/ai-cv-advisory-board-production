from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from advisory import web
from advisory.ai import OpenAiStructuredClient
from advisory.budget import BudgetExceededError, InMemoryBudgetLedger, Pricing
from advisory.interview import (
    CvDraft,
    DeterministicCvInterviewer,
    InterviewAnswer,
    InterviewQuestions,
    OpenAiCvInterviewer,
    run_budgeted,
)
from advisory.web import app

client = TestClient(app)
CV = (
    "EXPERIENCE\nSenior Engineer 2021-Present\n- Built Python services on Google Cloud.\n"
    "SKILLS\nPython, SQL\nEDUCATION\nBSc"
)


def _setup(user: str, *, job_text: str = "") -> tuple[dict[str, str], dict[str, object], dict[str, object]]:
    web.career_repository.clear()
    headers = {"x-advisory-user": user}
    version = client.post(
        "/api/cv-versions",
        headers=headers,
        data={"label": "Main CV"},
        files={"cv_file": ("cv.txt", CV.encode(), "text/plain")},
    ).json()
    application = client.post(
        "/api/applications",
        headers=headers,
        json={"company": "Lumenalta", "role": "AI Engineer", "cv_version_id": version["id"]},
    ).json()
    if job_text:
        client.post(
            f"/api/applications/{application['id']}/job-description",
            headers=headers,
            files={"job_file": ("job.txt", job_text.encode(), "text/plain")},
        )
    return headers, version, application


def test_guided_review_page_renders_steps_and_advisor_data() -> None:
    response = client.get("/review")
    assert response.status_code == 200
    assert 'id="advisors-data"' in response.text
    assert '"id": "recruiter"' in response.text
    assert "Answer a few questions. Get a stronger CV." in response.text


def test_board_review_is_saved_and_reopened() -> None:
    headers, version, application = _setup("guided-a", job_text="Python Kubernetes Terraform leadership")
    url = f"/api/applications/{application['id']}/board-review"
    assert client.get(url, headers=headers).status_code == 404
    assert client.post(url, headers=headers, data={"advisor_ids": ""}).status_code == 422

    saved = client.post(url, headers=headers, data={"advisor_ids": "recruiter,executive"})
    assert saved.status_code == 200
    body = saved.json()
    assert body["application"]["has_board_review"] is True
    assert "board_review" not in body["application"]
    report = body["board_review"]
    assert report["cv_version_id"] == version["id"]
    assert report["advisor_ids"] == ["recruiter", "executive"]
    assert [item["advisor_id"] for item in report["review"]["advisor_findings"]] == ["recruiter", "executive"]
    assert report["assessment"]["requirements"]

    listed = client.get("/api/applications", headers=headers).json()[0]
    assert listed["has_board_review"] is True
    assert listed["fit_score"] == report["review"]["fit_score"]
    reopened = client.get(url, headers=headers).json()
    assert reopened["board_review"]["review"] == report["review"]
    assert client.get(url, headers={"x-advisory-user": "someone-else"}).status_code == 404


def test_board_review_saves_pasted_description_and_requires_a_source() -> None:
    headers, _, application = _setup("guided-b")
    url = f"/api/applications/{application['id']}/board-review"
    missing = client.post(url, headers=headers, data={"advisor_ids": "recruiter"})
    assert missing.status_code == 422
    pasted = client.post(url, headers=headers, data={"advisor_ids": "recruiter", "job_text": "Python SQL"})
    assert pasted.status_code == 200
    assert pasted.json()["application"]["job_description_filename"] == "Pasted description"


def test_board_review_falls_back_when_the_model_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    headers, _, application = _setup("guided-c", job_text="Python Kubernetes")

    class Broken:
        def review_with_usage(self, *args: object) -> object:
            raise RuntimeError("provider down")

    monkeypatch.setattr(web, "member_ai_service", lambda: Broken())
    result = client.post(
        f"/api/applications/{application['id']}/board-review",
        headers=headers,
        data={"advisor_ids": "technical"},
    ).json()["board_review"]
    assert result["degraded"] is True
    assert "temporarily unavailable" in result["notice"]
    assert result["model"] == "rule-based"


def test_interview_questions_and_draft_flow() -> None:
    headers, version, application = _setup("guided-d", job_text="Python Kubernetes Terraform")
    questions = client.post(
        f"/api/cv-versions/{version['id']}/interview",
        headers=headers,
        data={"application_id": application["id"]},
    )
    assert questions.status_code == 200
    items = questions.json()["questions"]
    assert 1 <= len(items) <= 4
    assert any("kubernetes" in item["question"].lower() for item in items)

    draft_url = f"/api/cv-versions/{version['id']}/interview/draft"
    empty = client.post(draft_url, headers=headers, json={"answers": [{"question": "Q", "answer": " "}]})
    assert empty.status_code == 422
    draft = client.post(
        draft_url,
        headers=headers,
        json={
            "application_id": application["id"],
            "answers": [
                {"question": items[0]["question"], "answer": "Ran 12 services on GKE in production."}
            ],
        },
    )
    assert draft.status_code == 200
    cv_text = draft.json()["draft"]["cv_text"]
    assert "Built Python services on Google Cloud." in cv_text
    assert "Ran 12 services on GKE in production." in cv_text

    saved = client.post(
        f"/api/cv-versions/{version['id']}/revisions",
        headers=headers,
        data={"label": "Main CV · Lumenalta", "cv_text": cv_text},
    ).json()
    assert saved["parent_version_id"] == version["id"]
    assert client.post(
        f"/api/cv-versions/{version['id']}/interview", headers={"x-advisory-user": "intruder"}
    ).status_code == 404


def test_interview_uses_saved_review_gaps_without_a_job_description() -> None:
    headers, _, application = _setup("guided-e")
    client.post(
        f"/api/applications/{application['id']}/board-review",
        headers=headers,
        data={"advisor_ids": "recruiter", "job_text": "Python Terraform"},
    )
    context = web._interview_context("guided-e", application["id"])
    assert "Terraform" in context or "terraform" in context


def test_member_ai_falls_back_on_budget_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    headers, version, _ = _setup("guided-f")

    def exhausted(**kwargs: object) -> object:
        raise BudgetExceededError("Monthly AI budget reached")

    monkeypatch.setattr(web, "run_budgeted", exhausted)
    result = client.post(f"/api/cv-versions/{version['id']}/interview", headers=headers).json()
    assert result["questions"]
    assert "allowance is used up" in result["notice"]


def test_deterministic_interviewer_keeps_cv_and_appends_answers() -> None:
    interviewer = DeterministicCvInterviewer()
    questions, _, _ = interviewer.questions(CV, "")
    assert questions.questions
    unchanged, _, _ = interviewer.draft(CV, "", [InterviewAnswer(question="Q", answer="")])
    assert unchanged.cv_text == CV
    answers = [InterviewAnswer(question="Q", answer="Mentored  three   interns")]
    draft, _, _ = interviewer.draft(CV, "", answers)
    assert draft.cv_text.startswith(CV.rstrip())
    assert "- Mentored three interns" in draft.cv_text


def test_openai_interviewer_requests_strict_schemas_and_larger_draft_budget() -> None:
    captured: list[dict[str, object]] = []
    payloads = [
        InterviewQuestions.model_validate(
            {"questions": [{"question": f"Q{index}", "purpose": "p"} for index in range(6)]}
        ).model_dump_json(),
        CvDraft(cv_text="New CV", changes=["Added summary (CV)"]).model_dump_json(),
    ]

    class Completions:
        def create(self, **kwargs: object) -> object:
            captured.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(content=payloads.pop(0), refusal=None),
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
            )

    structured = OpenAiStructuredClient(
        api_key="test",
        model="gpt-6.1-terra",
        reasoning_effort="low",
        max_output_tokens=6_000,
        client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
    )
    interviewer = OpenAiCvInterviewer(structured, draft_output_tokens=12_000)
    questions, _, _ = interviewer.questions(CV, "Python")
    assert len(questions.questions) == 4
    draft, _, _ = interviewer.draft(CV, "Python", [InterviewAnswer(question="Q0", answer="A")])
    assert draft.cv_text == "New CV"
    assert captured[0]["max_completion_tokens"] == 6_000
    assert captured[1]["max_completion_tokens"] == 12_000
    assert "<interview>" in captured[1]["messages"][1]["content"]  # type: ignore[index]
    assert captured[1]["response_format"]["json_schema"]["strict"] is True  # type: ignore[index]


def test_run_budgeted_reconciles_and_releases() -> None:
    ledger = InMemoryBudgetLedger(10_000_000)
    emergency = InMemoryBudgetLedger(50_000_000)
    pricing = Pricing()
    result, usage = run_budgeted(
        ledger=ledger,
        owner_id="u",
        pricing=pricing,
        max_input_tokens=1_000,
        max_output_tokens=1_000,
        call=lambda: ("ok", 100, 50),
        event="ai.test",
        emergency_ledger=emergency,
    )
    assert result == "ok"
    assert ledger.snapshot("u").used_micro_usd == pricing.cost(100, 50) == usage.actual_micro_usd
    assert ledger.snapshot("u").reserved_micro_usd == 0

    def broken() -> tuple[str, int, int]:
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        run_budgeted(
            ledger=ledger,
            owner_id="u",
            pricing=pricing,
            max_input_tokens=1_000,
            max_output_tokens=1_000,
            call=broken,
            event="ai.test",
            emergency_ledger=emergency,
        )
    assert ledger.snapshot("u").reserved_micro_usd == 0
    assert emergency.snapshot("project-emergency-cap").reserved_micro_usd == 0
