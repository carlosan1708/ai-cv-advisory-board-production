from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ADVISORY_", env_file=".env", extra="ignore", populate_by_name=True
    )

    environment: Literal["demo", "local", "production"] = "local"
    max_input_chars: int = Field(default=30_000, ge=1_000, le=100_000)
    max_upload_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    max_job_page_bytes: int = Field(default=1_000_000, ge=10_000, le=5_000_000)
    app_name: str = "AI CV Advisory Board"
    public_origin: str = "https://ai-cv-advisory-board-production-142795288331.us-central1.run.app"
    repository_backend: Literal["memory", "firestore"] = "memory"
    auth_mode: Literal["development", "google"] = "development"
    google_oauth_client_id: str = ""
    admin_emails: str = "carlosan.1708@gmail.com"
    gcp_project: str = "ai-cv-advisory-board"
    gcp_location: str = "global"
    cv_bucket: str = "ai-cv-advisory-board-production-cvs"
    openai_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("ADVISORY_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    openai_model: str = "gpt-6-luna"
    openai_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] = "low"
    openai_input_micro_usd_per_million: int = Field(default=100_000, ge=1)
    openai_output_micro_usd_per_million: int = Field(default=500_000, ge=1)
    ai_max_input_tokens: int = Field(default=65_000, ge=1_000, le=400_000)
    ai_max_output_tokens: int = Field(default=6_000, ge=1_000, le=32_000)
    ai_monthly_limit_micro_usd: int = Field(default=5_000_000, ge=100_000, le=100_000_000)
    member_ai_monthly_limit_micro_usd: int = Field(
        default=10_000_000, ge=100_000, le=100_000_000
    )
    project_ai_monthly_limit_micro_usd: int = Field(
        default=50_000_000, ge=1_000_000, le=1_000_000_000
    )
    anonymous_ai_requests_per_minute: int = Field(default=2, ge=1, le=60)
    member_ai_requests_per_minute: int = Field(default=10, ge=1, le=120)

    @model_validator(mode="after")
    def production_must_use_real_identity(self) -> Settings:
        if self.environment == "production" and self.auth_mode != "google":
            raise ValueError("ADVISORY_AUTH_MODE must be 'google' when ADVISORY_ENVIRONMENT is 'production'")
        if self.environment == "production" and not self.openai_api_key.get_secret_value():
            raise ValueError("ADVISORY_OPENAI_API_KEY or OPENAI_API_KEY is required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
