from dataclasses import dataclass

from advisory.domain import Assessment, MatchPolicy
from advisory.observability import emit, operation


class InputError(ValueError):
    pass


@dataclass(frozen=True)
class AssessmentService:
    max_input_chars: int
    policy: MatchPolicy = MatchPolicy()

    def analyze(self, cv_text: str, job_text: str) -> tuple[str, Assessment]:
        cv_text = cv_text.strip()
        job_text = job_text.strip()
        if not cv_text or not job_text:
            raise InputError("CV and job description are required.")
        if len(cv_text) > self.max_input_chars or len(job_text) > self.max_input_chars:
            raise InputError(f"Each input must be at most {self.max_input_chars:,} characters.")
        with operation("assessment") as run_id:
            result = self.policy.assess(cv_text, job_text)
            emit(
                "assessment.completed",
                run_id=run_id,
                cv_chars=len(cv_text),
                job_chars=len(job_text),
                score=result.score,
                scoring_version=result.scoring_version,
            )
            return run_id, result

