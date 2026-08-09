from types import SimpleNamespace

import pytest

from advisory.ai import (
    BudgetedAiService,
    DeterministicAiReviewer,
    DeterministicCvReviewer,
    EvidenceReview,
    GeminiAiReviewer,
    UnrestrictedAiService,
    UnrestrictedCvService,
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
    reviewer.model = "gemini-3.5-flash-lite"
    review, input_tokens, output_tokens = reviewer.review("CV evidence", "Job needs")
    assert review == expected
    assert (input_tokens, output_tokens) == (500, 100)
    assert captured["model"] == "gemini-3.5-flash-lite"
    config = captured["config"]
    assert config.max_output_tokens == 1_024  # type: ignore[union-attr]
    assert config.response_mime_type == "application/json"  # type: ignore[union-attr]


def test_unrestricted_service_calls_reviewer_without_a_ledger() -> None:
    expected = EvidenceReview(
        fit_score=92,
        summary="Grounded",
        supported_strengths=["Python"],
        evidence_gaps=[],
        next_actions=["Verify evidence"],
    )

    class Reviewer:
        def review(self, cv_text: str, job_text: str) -> tuple[EvidenceReview, int, int]:
            assert (cv_text, job_text) == ("CV", "JOB")
            return expected, 20, 5

    assert UnrestrictedAiService(Reviewer()).review("member", "CV", "JOB") == expected


def test_standalone_cv_reviewer_scores_structure_and_unrestricted_service() -> None:
    reviewer = DeterministicCvReviewer()
    review, input_tokens, output_tokens = reviewer.review(
        "EXPERIENCE\nBuilt services for 50 teams\nSKILLS\nPython\nEDUCATION\nComputer Science"
    )
    assert review.quality_score >= 80
    assert "Includes quantified evidence" in review.strengths
    assert input_tokens == output_tokens == 0
    assert UnrestrictedCvService(reviewer).review("member", "EXPERIENCE\nBuilt systems").summary
