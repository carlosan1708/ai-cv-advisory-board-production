from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADVISORY_", env_file=".env", extra="ignore")

    environment: Literal["demo", "local", "production"] = "local"
    max_input_chars: int = Field(default=30_000, ge=1_000, le=100_000)
    max_upload_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    max_job_page_bytes: int = Field(default=1_000_000, ge=10_000, le=5_000_000)
    app_name: str = "AI CV Advisory Board"


@lru_cache
def get_settings() -> Settings:
    return Settings()
