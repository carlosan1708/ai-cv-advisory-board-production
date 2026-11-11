from types import SimpleNamespace

import pytest

from advisory.ai import (
    AiProviderError,
    BudgetedAiService,
    BudgetedCvService,
    DeterministicAiReviewer,
    DeterministicCvReviewer,
    EvidenceReview,
    OpenAiReviewer,
    OpenAiStructuredClient,
    verified_evidence,
)
from advisory.budget import BudgetExceededError, InMemoryBudgetLedger, Pricing


def test_deterministic_reviewer_is_bounded_and_grounded() -> None:
    review, input_tokens, output_tokens = DeterministicAiReviewer().review(
        "Built Python platform services", "Python Kubernetes platform leadership"
    )
    assert 0 <= review.fit_score <= 100
    assert any(item.startswith("python:") for item in review.supported_strengths)
    assert "kubernetes" in review.evidence_gaps
    assert input_tokens == output_tokens == 0


def test_budgeted_ai_service_reconciles_actual_usage() -> None:
    class Reviewer:
        def review(self, cv_text: str, job_text: str) -> tuple[EvidenceReview, int, int]:
            assert cv_text == "CV"
            assert job_text == "JOB"
            return (
                EvidenceReview(
                    fit_score=80,
                    summary="Grounded summary",
                    supported_strengths=["Python"],
                    evidence_gaps=["Kubernetes"],
                    next_actions=["Prepare evidence"],
                ),
                1_000,
                100,
            )

    ledger = InMemoryBudgetLedger(5_000_000)
    service = BudgetedAiService(Reviewer(), ledger)
    assert service.review("user", "CV", "JOB").fit_score == 80
    assert ledger.snapshot("user").used_micro_usd == Pricing().cost(1_000, 100)
    assert ledger.snapshot("user").reserved_micro_usd == 0


def test_budgeted_ai_service_releases_reservation_on_provider_failure() -> None:
    class BrokenReviewer:
        def review(self, cv_text: str, job_text: str) -> tuple[EvidenceReview, int, int]:
            raise RuntimeError("provider unavailable")

    ledger = InMemoryBudgetLedger(5_000_000)
    with pytest.raises(RuntimeError):
        BudgetedAiService(BrokenReviewer(), ledger).review("user", "CV", "JOB")
    assert ledger.snapshot("user").used_micro_usd == 0
    assert ledger.snapshot("user").reserved_micro_usd == 0


def test_budgeted_ai_service_rejects_before_provider_when_cap_is_too_small() -> None:
    class UnexpectedReviewer:
        def review(self, cv_text: str, job_text: str) -> tuple[EvidenceReview, int, int]:
            raise AssertionError("provider must not be called")

    with pytest.raises(BudgetExceededError):
        BudgetedAiService(UnexpectedReviewer(), InMemoryBudgetLedger(100)).review("user", "CV", "JOB")


def _fake_openai(  # type: ignore[no-untyped-def]
    payload: str, captured: dict[str, object], *, finish_reason: str = "stop", refusal: str | None = None
):
    class Completions:
        def create(self, **kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason=finish_reason,
                        message=SimpleNamespace(content=payload, refusal=refusal),
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=500, completion_tokens=100),
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


def _client(payload: str, captured: dict[str, object], **kwargs: object) -> OpenAiStructuredClient:
    return OpenAiStructuredClient(
        api_key="test",
        model="gpt-6-luna",
        reasoning_effort="low",
        max_output_tokens=6_000,
        client=_fake_openai(payload, captured, **kwargs),  # type: ignore[arg-type]
    )


def test_openai_adapter_requests_strict_json_schema() -> None:
    captured: dict[str, object] = {}
    expected = EvidenceReview(
        fit_score=70,
        summary="Evidence-led result",
        supported_strengths=["Python"],
        evidence_gaps=["Terraform"],
        next_actions=["Prepare an example"],
    )
    reviewer = OpenAiReviewer(_client(expected.model_dump_json(), captured))
    review, input_tokens, output_tokens = reviewer.review("CV evidence", "Job needs")
    assert review == expected
    assert (input_tokens, output_tokens) == (500, 100)
    assert captured["model"] == "gpt-6-luna"
    assert captured["max_completion_tokens"] == 6_000
    assert captured["reasoning_effort"] == "low"
    response_format = captured["response_format"]
    assert response_format["type"] == "json_schema"  # type: ignore[index]
    assert response_format["json_schema"]["strict"] is True  # type: ignore[index]
    schema = response_format["json_schema"]["schema"]  # type: ignore[index]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_openai_board_uses_only_selected_advisors_and_isolates_documents() -> None:
    captured: dict[str, object] = {}
    payload = EvidenceReview(
        fit_score=72,
        summary="Grounded board consensus",
        supported_strengths=["Python delivery"],
        evidence_gaps=["FinOps"],
        next_actions=["Quantify impact"],
    ).model_dump_json()
    reviewer = OpenAiReviewer(_client(payload, captured))
    review, _, _ = reviewer.review("CV", "JOB", ["executive", "impact", "unknown"])
    messages = captured["messages"]
    instructions = messages[0]["content"]  # type: ignore[index]
    assert messages[0]["role"] == "developer"  # type: ignore[index]
    assert "executive: Executive Story Editor" in instructions
    assert "impact: Impact & ROI Reviewer" in instructions
    assert "Technical Recruiter" not in instructions
    assert "<cv>\n" not in instructions
    assert messages[1]["content"].startswith("<cv>\nCV\n</cv>")  # type: ignore[index]
    assert [finding.advisor_id for finding in review.advisor_findings] == ["executive", "impact"]


def test_openai_adapter_raises_on_refusal_and_truncation() -> None:
    with pytest.raises(AiProviderError):
        OpenAiReviewer(_client("{}", {}, refusal="no")).review("CV", "JOB")
    with pytest.raises(AiProviderError):
        OpenAiReviewer(_client("{}", {}, finish_reason="length")).review("CV", "JOB")


def test_unverifiable_quotes_are_removed_from_advisor_findings() -> None:
    review = EvidenceReview.model_validate(
        {
            "fit_score": 60,
            "summary": "s",
            "supported_strengths": [],
            "evidence_gaps": [],
            "next_actions": [],
            "advisor_findings": [
                {
                    "advisor_id": "technical",
                    "headline": "h",
                    "finding": "f",
                    "evidence": ['"Built   Python APIs"', "Led a team of 40 engineers"],
                    "recommendation": "r",
                }
            ],
        }
    )
    checked = verified_evidence(review, "EXPERIENCE\n- Built Python APIs on Google Cloud.")
    assert checked.advisor_findings[0].evidence == ['"Built   Python APIs"']


def test_deterministic_panel_gives_distinct_grounded_findings() -> None:
    cv = (
        "EXPERIENCE\n- Built Python APIs serving 2 million users.\n"
        "- Led a team of 5 engineers and mentored two juniors.\n"
        "SKILLS\nPython, SQL\nEDUCATION\nBSc"
    )
    review, _, _ = DeterministicAiReviewer().review(
        cv, "Python SQL Kubernetes leadership", ["recruiter", "executive", "impact"]
    )
    headlines = [finding.headline for finding in review.advisor_findings]
    assert len(set(headlines)) == 3
    for finding in review.advisor_findings:
        for quote in finding.evidence:
            assert quote in cv
    assert all("need" not in question.split() for question in review.interview_questions)


def test_ai_review_truncates_provider_output_to_safe_schema_bounds() -> None:
    review = EvidenceReview.model_validate(
        {
            "fit_score": 140,
            "summary": "s" * 900,
            "supported_strengths": ["strength" * 50] * 7,
            "evidence_gaps": ["gap"] * 8,
            "next_actions": ["action"] * 7,
            "advisor_findings": [
                {
                    "advisor_id": "technical" * 10,
                    "headline": "headline" * 30,
                    "finding": "finding" * 100,
                    "evidence": ["evidence" * 50] * 4,
                    "recommendation": "recommend" * 60,
                }
            ]
            * 5,
            "tailoring_moves": [
                {"section": "Experience", "change": "change" * 100, "reason": "reason" * 100}
            ]
            * 7,
            "interview_questions": ["question" * 80] * 7,
        }
    )
    assert review.fit_score == 100
    assert len(review.summary) == 700
    assert len(review.supported_strengths) == 5
    assert len(review.advisor_findings) == 3
    assert len(review.advisor_findings[0].evidence) == 2
    assert len(review.tailoring_moves) == 4
    assert len(review.interview_questions) == 4


def test_budgeted_service_enforces_user_and_project_caps() -> None:
    expected = EvidenceReview(
        fit_score=90,
        summary="Grounded",
        supported_strengths=["Python"],
        evidence_gaps=[],
        next_actions=["Verify"],
    )

    class Reviewer:
        def review(self, cv_text: str, job_text: str) -> tuple[EvidenceReview, int, int]:
            return expected, 100, 10

    user_ledger = InMemoryBudgetLedger(1_000_000)
    project_ledger = InMemoryBudgetLedger(100)
    service = BudgetedAiService(Reviewer(), user_ledger, emergency_ledger=project_ledger)
    with pytest.raises(BudgetExceededError):
        service.review("member", "CV", "JOB")
    assert user_ledger.snapshot("member").reserved_micro_usd == 0


def test_budgeted_cv_service_reconciles_both_ledgers() -> None:
    reviewer = DeterministicCvReviewer()
    user_ledger = InMemoryBudgetLedger(10_000_000)
    project_ledger = InMemoryBudgetLedger(50_000_000)
    service = BudgetedCvService(reviewer, user_ledger, emergency_ledger=project_ledger)
    assert service.review("member", "EXPERIENCE\nBuilt systems").summary
    assert user_ledger.snapshot("member").reserved_micro_usd == 0
    assert project_ledger.snapshot("project-emergency-cap").reserved_micro_usd == 0


def test_standalone_cv_reviewer_scores_structure() -> None:
    reviewer = DeterministicCvReviewer()
    review, input_tokens, output_tokens = reviewer.review(
        "EXPERIENCE\nBuilt services for 50 teams\nSKILLS\nPython\nEDUCATION\nComputer Science"
    )
    assert review.quality_score >= 80
    assert "Includes quantified evidence" in review.strengths
    assert input_tokens == output_tokens == 0


def test_requirement_ledger_keeps_only_verified_quotes() -> None:
    review = EvidenceReview.model_validate(
        {
            "fit_score": 70,
            "summary": "s",
            "supported_strengths": [],
            "evidence_gaps": [],
            "next_actions": [],
            "requirements": [
                {
                    "requirement": "LangGraph agents",
                    "supported": True,
                    "evidence": "Built agents with LangGraph.",
                },
                {"requirement": "Kubernetes", "supported": True, "evidence": "Ran Kubernetes at scale."},
                {"requirement": "Terraform", "supported": False, "evidence": "anything"},
            ],
        }
    )
    cv = "EXPERIENCE\n- Built agents\nwith LangGraph.\nSKILLS\nPython"
    checked = verified_evidence(review, cv).requirements
    assert [(item.requirement, item.supported, item.evidence) for item in checked] == [
        ("LangGraph agents", True, "Built agents with LangGraph."),
        ("Kubernetes", False, ""),
        ("Terraform", False, ""),
    ]


def test_deterministic_reviewer_fills_the_requirement_ledger() -> None:
    review, _, _ = DeterministicAiReviewer().review("EXPERIENCE\nBuilt Python services", "Python Kubernetes")
    assert [(item.requirement, item.supported) for item in review.requirements] == [
        ("python", True),
        ("kubernetes", False),
    ]
