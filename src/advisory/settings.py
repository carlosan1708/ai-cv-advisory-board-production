from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADVISORY_", env_file=".env", extra="ignore")

    environment: Literal["demo", "local", "production"] = "local"
    max_input_chars: int = Field(default=30_000, ge=1_000, le=100_000)
    app_name: str = "AI CV Advisory Board"


@lru_cache
def get_settings() -> Settings:
    return Settings()

