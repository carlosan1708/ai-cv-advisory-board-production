from __future__ import annotations

from time import monotonic
from typing import Protocol

from pydantic import BaseModel, Field

from advisory.budget import BudgetLedger, Pricing
from advisory.observability import emit


class EvidenceReview(BaseModel):
    fit_score: int = Field(ge=0, le=100)
    summary: str = Field(max_length=700)
    supported_strengths: list[str] = Field(max_length=5)
    evidence_gaps: list[str] = Field(max_length=5)
    next_actions: list[str] = Field(max_length=4)


class AiReviewer(Protocol):
    def review(self, cv_text: str, job_text: str) -> tuple[EvidenceReview, int, int]: ...


class DeterministicAiReviewer:
    def review(self, cv_text: str, job_text: str) -> tuple[EvidenceReview, int, int]:
        cv_words = {word.lower().strip(".,:;()") for word in cv_text.split() if len(word) > 3}
        job_words = {word.lower().strip(".,:;()") for word in job_text.split() if len(word) > 3}
        overlap = sorted(cv_words & job_words)[:5]
        gaps = sorted(job_words - cv_words)[:5]
        denominator = max(1, len(job_words))
        score = min(100, round(len(cv_words & job_words) / denominator * 100))
        review = EvidenceReview(
            fit_score=score,
            summary="A deterministic evidence check is shown while Gemini is unavailable.",
            supported_strengths=overlap or ["No direct keyword evidence found"],
            evidence_gaps=gaps,
            next_actions=["Verify each suggested claim against the attached CV."],
        )
        return review, 0, 0


class GeminiAiReviewer:
    def __init__(self, *, project: str, location: str, model: str) -> None:
        from google import genai

        self.client = genai.Client(vertexai=True, project=project, location=location)
        self.model = model

    def review(self, cv_text: str, job_text: str) -> tuple[EvidenceReview, int, int]:
        from google.genai import types

        prompt = f"""You are an evidence auditor for a job application.
Return only the requested JSON. Never invent candidate experience. A strength is allowed only when the CV
contains direct evidence. Keep the summary under 80 words and every list item under 25 words.

CV:
{cv_text}

JOB DESCRIPTION:
{job_text}
"""
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EvidenceReview,
                max_output_tokens=1_024,
                temperature=0.1,
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
            ),
        )
        review = response.parsed
        if not isinstance(review, EvidenceReview):
            review = EvidenceReview.model_validate_json(response.text or "{}")
        usage = response.usage_metadata
        input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0) + int(
            getattr(usage, "thoughts_token_count", 0) or 0
        )
        return review, input_tokens, output_tokens


class BudgetedAiService:
    def __init__(
        self,
        reviewer: AiReviewer,
        ledger: BudgetLedger,
        *,
        pricing: Pricing | None = None,
        max_input_tokens: int = 65_000,
        max_output_tokens: int = 1_024,
    ) -> None:
        self.reviewer = reviewer
        self.ledger = ledger
        self.pricing = pricing or Pricing()
        self.maximum_cost = self.pricing.cost(max_input_tokens, max_output_tokens)

    def review(self, owner_id: str, cv_text: str, job_text: str) -> EvidenceReview:
        reservation = self.ledger.reserve(owner_id, self.maximum_cost)
        started = monotonic()
        try:
            review, input_tokens, output_tokens = self.reviewer.review(cv_text, job_text)
            actual_cost = self.pricing.cost(input_tokens, output_tokens)
            self.ledger.reconcile(reservation, actual_cost)
            emit(
                "gemini.request.completed",
                user_id=owner_id,
                model=self.pricing.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                actual_micro_usd=actual_cost,
                duration_ms=round((monotonic() - started) * 1_000),
            )
            return review
        except Exception:
            self.ledger.release(reservation)
            emit("gemini.request.failed", user_id=owner_id, model=self.pricing.model)
            raise
