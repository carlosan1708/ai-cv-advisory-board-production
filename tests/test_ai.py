from types import SimpleNamespace

import pytest

from advisory.ai import (
    BudgetedAiService,
    BudgetedCvService,
    DeterministicAiReviewer,
    DeterministicCvReviewer,
    EvidenceReview,
    GeminiAiReviewer,
)
from advisory.budget import BudgetExceededError, InMemoryBudgetLedger, Pricing


def test_deterministic_reviewer_is_bounded_and_grounded() -> None:
    review, input_tokens, output_tokens = DeterministicAiReviewer().review(
        "Built Python platform services", "Python Kubernetes platform leadership"
    )
    assert 0 <= review.fit_score <= 100
    assert "python" in review.supported_strengths
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


def test_gemini_adapter_requests_strict_bounded_json() -> None:
    captured: dict[str, object] = {}
    expected = EvidenceReview(
        fit_score=70,
        summary="Evidence-led result",
        supported_strengths=["Python"],
        evidence_gaps=["Terraform"],
        next_actions=["Prepare an example"],
    )

    class Models:
        def generate_content(self, **kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            return SimpleNamespace(
                parsed=expected,
                text=expected.model_dump_json(),
                usage_metadata=SimpleNamespace(
                    prompt_token_count=500,
                    candidates_token_count=80,
                    thoughts_token_count=20,
                ),
            )

    reviewer = GeminiAiReviewer.__new__(GeminiAiReviewer)
    reviewer.client = SimpleNamespace(models=Models())
    reviewer.model = "gemini-2.5-flash"
    review, input_tokens, output_tokens = reviewer.review("CV evidence", "Job needs")
    assert review == expected
    assert (input_tokens, output_tokens) == (500, 100)
    assert captured["model"] == "gemini-2.5-flash"
    config = captured["config"]
    assert config.max_output_tokens == 2_048  # type: ignore[union-attr]
    assert config.response_mime_type == "application/json"  # type: ignore[union-attr]


def test_gemini_board_uses_only_selected_advisor_briefs() -> None:
    captured: dict[str, object] = {}
    expected = EvidenceReview(
        fit_score=72,
        summary="Grounded board consensus",
        supported_strengths=["Python delivery"],
        evidence_gaps=["FinOps"],
        next_actions=["Quantify impact"],
    )

    class Models:
        def generate_content(self, **kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            return SimpleNamespace(
                parsed=expected,
                text=expected.model_dump_json(),
                usage_metadata=SimpleNamespace(
                    prompt_token_count=400,
                    candidates_token_count=100,
                    thoughts_token_count=0,
                ),
            )

    reviewer = GeminiAiReviewer.__new__(GeminiAiReviewer)
    reviewer.client = SimpleNamespace(models=Models())
    reviewer.model = "gemini-2.5-flash"
    review, _, _ = reviewer.review("CV", "JOB", ["executive", "impact", "unknown"])
    prompt = str(captured["contents"])
    assert "executive: Executive Story Editor" in prompt
    assert "impact: Impact & ROI Reviewer" in prompt
    assert "Technical Recruiter" not in prompt
    assert [finding.advisor_id for finding in review.advisor_findings] == ["executive", "impact"]


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
