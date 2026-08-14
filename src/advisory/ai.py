from __future__ import annotations

from time import monotonic
from typing import Protocol

from pydantic import BaseModel, Field, field_validator

from advisory.advisors import advisor_context, normalize_advisor_ids
from advisory.budget import BudgetLedger, Pricing
from advisory.observability import emit


class AdvisorFinding(BaseModel):
    advisor_id: str = Field(max_length=32)
    headline: str = Field(max_length=140)
    finding: str = Field(max_length=420)
    evidence: list[str] = Field(max_length=2)
    recommendation: str = Field(max_length=260)

    @field_validator("advisor_id", mode="before")
    @classmethod
    def bound_advisor_id(cls, value: object) -> str:
        return str(value)[:32]

    @field_validator("headline", mode="before")
    @classmethod
    def bound_headline(cls, value: object) -> str:
        return str(value)[:140]

    @field_validator("finding", mode="before")
    @classmethod
    def bound_finding(cls, value: object) -> str:
        return str(value)[:420]

    @field_validator("recommendation", mode="before")
    @classmethod
    def bound_recommendation(cls, value: object) -> str:
        return str(value)[:260]

    @field_validator("evidence", mode="before")
    @classmethod
    def bound_evidence(cls, value: object) -> list[str]:
        return [str(item)[:240] for item in value[:2]] if isinstance(value, list) else []


class TailoringMove(BaseModel):
    section: str = Field(max_length=80)
    change: str = Field(max_length=260)
    reason: str = Field(max_length=220)

    @field_validator("section", mode="before")
    @classmethod
    def bound_section(cls, value: object) -> str:
        return str(value)[:80]

    @field_validator("change", mode="before")
    @classmethod
    def bound_change(cls, value: object) -> str:
        return str(value)[:260]

    @field_validator("reason", mode="before")
    @classmethod
    def bound_reason(cls, value: object) -> str:
        return str(value)[:220]


class EvidenceReview(BaseModel):
    fit_score: int = Field(ge=0, le=100)
    summary: str = Field(max_length=700)
    supported_strengths: list[str] = Field(max_length=5)
    evidence_gaps: list[str] = Field(max_length=5)
    next_actions: list[str] = Field(max_length=4)
    advisor_findings: list[AdvisorFinding] = Field(default_factory=list, max_length=3)
    tailoring_moves: list[TailoringMove] = Field(default_factory=list, max_length=4)
    interview_questions: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("fit_score", mode="before")
    @classmethod
    def bound_fit_score(cls, value: object) -> int:
        if not isinstance(value, int | float | str):
            return 0
        try:
            return max(0, min(100, int(value)))
        except (TypeError, ValueError):
            return 0

    @field_validator("summary", mode="before")
    @classmethod
    def bound_summary(cls, value: object) -> str:
        return str(value)[:700]

    @field_validator("supported_strengths", "evidence_gaps", mode="before")
    @classmethod
    def bound_five_item_lists(cls, value: object) -> list[str]:
        return [str(item)[:240] for item in value[:5]] if isinstance(value, list) else []

    @field_validator("next_actions", "interview_questions", mode="before")
    @classmethod
    def bound_four_item_lists(cls, value: object) -> list[str]:
        return [str(item)[:260] for item in value[:4]] if isinstance(value, list) else []

    @field_validator("advisor_findings", mode="before")
    @classmethod
    def bound_advisor_findings(cls, value: object) -> list[object]:
        return value[:3] if isinstance(value, list) else []

    @field_validator("tailoring_moves", mode="before")
    @classmethod
    def bound_tailoring_moves(cls, value: object) -> list[object]:
        return value[:4] if isinstance(value, list) else []


class CvReview(BaseModel):
    quality_score: int = Field(ge=0, le=100)
    summary: str = Field(max_length=700)
    strengths: list[str] = Field(max_length=5)
    improvement_areas: list[str] = Field(max_length=5)
    next_actions: list[str] = Field(max_length=5)


class AiReviewer(Protocol):
    def review(
        self, cv_text: str, job_text: str, advisor_ids: list[str] | None = None
    ) -> tuple[EvidenceReview, int, int]: ...


class CvReviewer(Protocol):
    def review(self, cv_text: str) -> tuple[CvReview, int, int]: ...


class DeterministicAiReviewer:
    def review(
        self, cv_text: str, job_text: str, advisor_ids: list[str] | None = None
    ) -> tuple[EvidenceReview, int, int]:
        cv_words = {word.lower().strip(".,:;()") for word in cv_text.split() if len(word) > 3}
        job_words = {word.lower().strip(".,:;()") for word in job_text.split() if len(word) > 3}
        overlap = sorted(cv_words & job_words)[:5]
        gaps = sorted(job_words - cv_words)[:5]
        denominator = max(1, len(job_words))
        score = min(100, round(len(cv_words & job_words) / denominator * 100))
        selected_advisors = advisor_context(advisor_ids)
        review = EvidenceReview(
            fit_score=score,
            summary=(
                "A grounded deterministic evidence check is shown when a model call is not used. "
                "Treat shared language as a starting point and verify the deeper context yourself."
            ),
            supported_strengths=overlap or ["No direct keyword evidence found"],
            evidence_gaps=gaps,
            next_actions=["Verify each suggested claim against the attached CV."],
            advisor_findings=[
                AdvisorFinding(
                    advisor_id=advisor["id"],
                    headline=f"{advisor['role']} evidence check",
                    finding=(
                        "The deterministic fallback found shared role language "
                        "but cannot infer deeper context."
                    ),
                    evidence=overlap[:2] or ["No direct shared term was found"],
                    recommendation=f"Review the CV for {advisor['focus']}.",
                )
                for advisor in selected_advisors
            ],
            tailoring_moves=[
                TailoringMove(
                    section="Experience",
                    change=(
                        "Add truthful scope, outcomes, and role-relevant language "
                        "where the CV supports it."
                    ),
                    reason="Specific evidence is more credible than keyword repetition.",
                )
            ],
            interview_questions=[
                f"What direct example demonstrates your experience with {gap}?" for gap in gaps[:3]
            ],
        )
        return review, 0, 0


class GeminiAiReviewer:
    def __init__(self, *, project: str, location: str, model: str) -> None:
        from google import genai

        self.client = genai.Client(vertexai=True, project=project, location=location)
        self.model = model

    def review(
        self, cv_text: str, job_text: str, advisor_ids: list[str] | None = None
    ) -> tuple[EvidenceReview, int, int]:
        from google.genai import types

        selected_advisors = advisor_context(advisor_ids)
        advisor_brief = "\n".join(
            f"- {item['id']}: {item['name']} ({item['role']}); focus on {item['focus']}"
            for item in selected_advisors
        )
        prompt = f"""You chair an AI CV advisory board reviewing one CV against one job.
Return only the requested JSON. Never invent, embellish, or infer candidate experience. A strength, finding,
or suggested change is allowed only when the CV contains direct support. Quote short CV evidence in each
advisor finding. If evidence is absent, name the gap instead of manufacturing a claim.

The user selected these advisors. Return exactly one advisor_findings entry for each ID, in this order:
{advisor_brief}

Make the report practical and specific:
- summary: board consensus in under 90 words.
- advisor findings: distinct perspective, direct evidence, and one recommendation each.
- tailoring moves: safe edits to emphasis, ordering, clarity, or wording; never add new experience.
- interview questions: questions the candidate should prepare from gaps or important evidence.
- use at most five strengths, five gaps, four next actions, four tailoring moves, and four questions.
- keep every list item under 35 words and the entire response useful without follow-up.

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
                max_output_tokens=2_048,
                temperature=0.1,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        review = response.parsed
        if not isinstance(review, EvidenceReview):
            review = EvidenceReview.model_validate_json(response.text or "{}")
        selected_ids = [item["id"] for item in selected_advisors]
        if advisor_ids is not None and selected_ids:
            returned_findings = {finding.advisor_id: finding for finding in review.advisor_findings}
            deterministic_review, _, _ = DeterministicAiReviewer().review(
                cv_text, job_text, selected_ids
            )
            fallback_findings = {
                finding.advisor_id: finding for finding in deterministic_review.advisor_findings
            }
            review = review.model_copy(
                update={
                    "advisor_findings": [
                        returned_findings.get(advisor_id, fallback_findings[advisor_id])
                        for advisor_id in selected_ids
                    ]
                }
            )
        usage = response.usage_metadata
        input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0) + int(
            getattr(usage, "thoughts_token_count", 0) or 0
        )
        return review, input_tokens, output_tokens


class DeterministicCvReviewer:
    def review(self, cv_text: str) -> tuple[CvReview, int, int]:
        lowered = cv_text.casefold()
        strengths = []
        if "experience" in lowered:
            strengths.append("Experience is clearly identified")
        if "skills" in lowered:
            strengths.append("Skills are easy to locate")
        if any(character.isdigit() for character in cv_text):
            strengths.append("Includes quantified evidence")
        gaps = []
        if not any(character.isdigit() for character in cv_text):
            gaps.append("Add truthful metrics or scale where available")
        if "education" not in lowered:
            gaps.append("Clarify education or relevant credentials")
        score = min(100, 45 + len(strengths) * 15 - len(gaps) * 5)
        return (
            CvReview(
                quality_score=score,
                summary="A structural CV check is shown while Gemini is unavailable.",
                strengths=strengths or ["The CV contains readable text"],
                improvement_areas=gaps or ["Tighten bullets around outcomes and evidence"],
                next_actions=["Review every change for accuracy before saving a new version"],
            ),
            0,
            0,
        )


class GeminiCvReviewer:
    def __init__(self, *, project: str, location: str, model: str) -> None:
        from google import genai

        self.client = genai.Client(vertexai=True, project=project, location=location)
        self.model = model

    def review(self, cv_text: str) -> tuple[CvReview, int, int]:
        from google.genai import types

        prompt = f"""Audit this CV as a standalone professional document. Do not assume a target job.
Return only the requested JSON. Never invent experience. Evaluate clarity, evidence, structure, specificity,
and seniority signaling. Keep the summary under 80 words and list items under 25 words.

CV:
{cv_text}
"""
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CvReview,
                max_output_tokens=1_024,
                temperature=0.1,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        review = response.parsed
        if not isinstance(review, CvReview):
            review = CvReview.model_validate_json(response.text or "{}")
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
        max_output_tokens: int = 2_048,
        emergency_ledger: BudgetLedger | None = None,
        emergency_owner_id: str = "project-emergency-cap",
    ) -> None:
        self.reviewer = reviewer
        self.ledger = ledger
        self.pricing = pricing or Pricing()
        self.maximum_cost = self.pricing.cost(max_input_tokens, max_output_tokens)
        self.emergency_ledger = emergency_ledger
        self.emergency_owner_id = emergency_owner_id

    def review(
        self,
        owner_id: str,
        cv_text: str,
        job_text: str,
        advisor_ids: list[str] | None = None,
    ) -> EvidenceReview:
        reservation = self.ledger.reserve(owner_id, self.maximum_cost)
        emergency_reservation = None
        if self.emergency_ledger is not None:
            try:
                emergency_reservation = self.emergency_ledger.reserve(
                    self.emergency_owner_id, self.maximum_cost
                )
            except Exception:
                self.ledger.release(reservation)
                raise
        started = monotonic()
        try:
            if advisor_ids is None:
                review, input_tokens, output_tokens = self.reviewer.review(cv_text, job_text)
            else:
                review, input_tokens, output_tokens = self.reviewer.review(
                    cv_text, job_text, normalize_advisor_ids(advisor_ids)
                )
            actual_cost = self.pricing.cost(input_tokens, output_tokens)
            self.ledger.reconcile(reservation, actual_cost)
            if self.emergency_ledger is not None and emergency_reservation is not None:
                self.emergency_ledger.reconcile(emergency_reservation, actual_cost)
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
            try:
                self.ledger.release(reservation)
            except ValueError:
                pass
            if self.emergency_ledger is not None and emergency_reservation is not None:
                try:
                    self.emergency_ledger.release(emergency_reservation)
                except ValueError:
                    pass
            emit("gemini.request.failed", user_id=owner_id, model=self.pricing.model)
            raise


class BudgetedCvService:
    def __init__(
        self,
        reviewer: CvReviewer,
        ledger: BudgetLedger,
        *,
        pricing: Pricing | None = None,
        max_input_tokens: int = 65_000,
        max_output_tokens: int = 1_024,
        emergency_ledger: BudgetLedger | None = None,
        emergency_owner_id: str = "project-emergency-cap",
    ) -> None:
        self.reviewer = reviewer
        self.ledger = ledger
        self.pricing = pricing or Pricing()
        self.maximum_cost = self.pricing.cost(max_input_tokens, max_output_tokens)
        self.emergency_ledger = emergency_ledger
        self.emergency_owner_id = emergency_owner_id

    def review(self, owner_id: str, cv_text: str) -> CvReview:
        reservation = self.ledger.reserve(owner_id, self.maximum_cost)
        emergency_reservation = None
        if self.emergency_ledger is not None:
            try:
                emergency_reservation = self.emergency_ledger.reserve(
                    self.emergency_owner_id, self.maximum_cost
                )
            except Exception:
                self.ledger.release(reservation)
                raise
        started = monotonic()
        try:
            review, input_tokens, output_tokens = self.reviewer.review(cv_text)
            actual_cost = self.pricing.cost(input_tokens, output_tokens)
            self.ledger.reconcile(reservation, actual_cost)
            if self.emergency_ledger is not None and emergency_reservation is not None:
                self.emergency_ledger.reconcile(emergency_reservation, actual_cost)
            emit(
                "gemini.cv_review.completed",
                user_id=owner_id,
                access_tier="approved",
                model=self.pricing.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                actual_micro_usd=actual_cost,
                duration_ms=round((monotonic() - started) * 1_000),
            )
            return review
        except Exception:
            try:
                self.ledger.release(reservation)
            except ValueError:
                pass
            if self.emergency_ledger is not None and emergency_reservation is not None:
                try:
                    self.emergency_ledger.release(emergency_reservation)
                except ValueError:
                    pass
            emit("gemini.cv_review.failed", user_id=owner_id, model=self.pricing.model)
            raise
