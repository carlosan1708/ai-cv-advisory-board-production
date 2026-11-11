"""Read the role and company from a job posting so the user does not have to type them."""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import BaseModel, Field, field_validator

from advisory.ai import UNTRUSTED_DOCUMENTS_RULE, OpenAiStructuredClient, _strict_object

PREVIEW_CHARS = 6_000
_ROLE_HINT = re.compile(
    r"\b(engineer|developer|manager|designer|analyst|scientist|lead|architect|director|specialist|consultant"
    r"|intern|head|officer|administrator|coordinator|researcher)\b",
    re.IGNORECASE,
)


class JobIdentity(BaseModel):
    role: str = Field(default="", max_length=160)
    company: str = Field(default="", max_length=120)

    @field_validator("role", mode="before")
    @classmethod
    def bound_role(cls, value: object) -> str:
        return " ".join(str(value or "").split())[:160]

    @field_validator("company", mode="before")
    @classmethod
    def bound_company(cls, value: object) -> str:
        return " ".join(str(value or "").split())[:120]


IDENTITY_SCHEMA = _strict_object({"role": {"type": "string"}, "company": {"type": "string"}})


class JobIdentifier(Protocol):
    def identify(self, job_text: str) -> tuple[JobIdentity, int, int]: ...


class HeuristicJobIdentifier:
    """No-AI fallback: the first short line that looks like a job title."""

    def identify(self, job_text: str) -> tuple[JobIdentity, int, int]:
        for line in job_text.splitlines()[:15]:
            cleaned = " ".join(line.split())
            if 3 <= len(cleaned) <= 90 and _ROLE_HINT.search(cleaned):
                role, _, company = cleaned.partition(" at ")
                return JobIdentity(role=role.rstrip(" :-"), company=company.rstrip(" .")), 0, 0
        return JobIdentity(), 0, 0


class OpenAiJobIdentifier:
    def __init__(self, client: OpenAiStructuredClient) -> None:
        self.client = client

    def identify(self, job_text: str) -> tuple[JobIdentity, int, int]:
        instructions = f"""Read the job posting and return the job title (role) and the hiring company's name.
{UNTRUSTED_DOCUMENTS_RULE}
Use the posting's own wording. If the company or role is not stated, return an empty string for it.
Never guess a company from a recruiter or job-board name."""
        content, input_tokens, output_tokens = self.client.complete(
            instructions=instructions,
            documents=f"<job_description>\n{job_text[:PREVIEW_CHARS]}\n</job_description>",
            schema_name="job_identity",
            schema=IDENTITY_SCHEMA,
            max_output_tokens=1_500,
        )
        return JobIdentity.model_validate_json(content), input_tokens, output_tokens
