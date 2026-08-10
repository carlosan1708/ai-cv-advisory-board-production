from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class ApplicationStatus(StrEnum):
    INTERESTED = "interested"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    CLOSED = "closed"


class ApplicationCreate(BaseModel):
    company: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=160)
    status: ApplicationStatus = ApplicationStatus.INTERESTED
    job_url: str = Field(default="", max_length=2_000)
    location: str = Field(default="", max_length=160)
    source: str = Field(default="", max_length=120)
    applied_date: date | None = None
    next_action: str = Field(default="", max_length=500)
    next_action_due: date | None = None
    cv_version_id: str | None = Field(default=None, max_length=64)
    notes: str = Field(default="", max_length=10_000)

    @field_validator("company", "role")
    @classmethod
    def required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("job_url")
    @classmethod
    def public_https_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return ""
        parsed = urlparse(cleaned)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("must be a complete HTTPS URL")
        return cleaned

    @field_validator("location", "source", "next_action", "notes")
    @classmethod
    def clean_optional_text(cls, value: str) -> str:
        return value.strip()


class ApplicationUpdate(BaseModel):
    company: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, min_length=1, max_length=160)
    status: ApplicationStatus | None = None
    job_url: str | None = Field(default=None, max_length=2_000)
    location: str | None = Field(default=None, max_length=160)
    source: str | None = Field(default=None, max_length=120)
    applied_date: date | None = None
    next_action: str | None = Field(default=None, max_length=500)
    next_action_due: date | None = None
    cv_version_id: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=10_000)
    fit_score: int | None = Field(default=None, ge=0, le=100)
    ai_summary: str | None = Field(default=None, max_length=700)

    @field_validator("company", "role")
    @classmethod
    def non_blank_if_present(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("job_url")
    @classmethod
    def valid_url_if_present(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return value.strip() if value else value
        parsed = urlparse(value.strip())
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("must be a complete HTTPS URL")
        return value.strip()


class Application(ApplicationCreate):
    id: str
    owner_id: str
    fit_score: int | None = Field(default=None, ge=0, le=100)
    ai_summary: str = ""
    archive_id: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def new(cls, owner_id: str, payload: ApplicationCreate) -> Application:
        now = datetime.now(UTC)
        return cls(
            id=uuid4().hex,
            owner_id=owner_id,
            created_at=now,
            updated_at=now,
            **payload.model_dump(),
        )


class CvVersion(BaseModel):
    id: str
    owner_id: str
    label: str
    filename: str
    content_type: str
    byte_count: int
    sha256: str
    extracted_text: str
    parent_version_id: str | None = None
    archive_id: str | None = None
    created_at: datetime


class WorkspaceArchive(BaseModel):
    id: str
    owner_id: str
    label: str = Field(min_length=1, max_length=120)
    application_count: int = Field(ge=0)
    cv_version_count: int = Field(ge=0)
    created_at: datetime


class WorkspaceArchiveDetail(BaseModel):
    archive: WorkspaceArchive
    applications: list[Application]
    cv_versions: list[CvVersion]
