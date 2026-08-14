from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

AuditTier = Literal["anonymous", "approved"]
AuditReviewType = Literal["job_match", "application", "cv"]
AuditStatus = Literal[
    "gemini",
    "fallback",
    "budget_limited",
    "rate_limited",
    "provider_error",
]


class AiAuditEvent(BaseModel):
    """Privacy-safe operational metadata. Source documents and AI prose are never stored."""

    id: str
    created_at: datetime
    owner_id: str = Field(max_length=160)
    access_tier: AuditTier
    review_type: AuditReviewType
    status: AuditStatus
    model: str = Field(max_length=80)
    advisor_ids: list[str] = Field(default_factory=list, max_length=3)
    score: int | None = Field(default=None, ge=0, le=100)
    band: str = Field(default="", max_length=32)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    actual_micro_usd: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)

    @classmethod
    def new(
        cls,
        *,
        owner_id: str,
        access_tier: AuditTier,
        review_type: AuditReviewType,
        status: AuditStatus,
        model: str,
        advisor_ids: list[str] | None = None,
        score: int | None = None,
        band: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        actual_micro_usd: int = 0,
        duration_ms: int = 0,
    ) -> AiAuditEvent:
        return cls(
            id=uuid4().hex,
            created_at=datetime.now(UTC),
            owner_id=owner_id,
            access_tier=access_tier,
            review_type=review_type,
            status=status,
            model=model,
            advisor_ids=(advisor_ids or [])[:3],
            score=score,
            band=band,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            actual_micro_usd=actual_micro_usd,
            duration_ms=duration_ms,
        )


class AiAuditRepository(Protocol):
    def record(self, event: AiAuditEvent) -> None: ...
    def list_recent(self, limit: int = 50) -> list[AiAuditEvent]: ...
    def count_since(self, since: datetime) -> int: ...


class InMemoryAiAuditRepository:
    def __init__(self) -> None:
        self._events: list[AiAuditEvent] = []
        self._lock = RLock()

    def record(self, event: AiAuditEvent) -> None:
        with self._lock:
            self._events.append(event.model_copy(deep=True))

    def list_recent(self, limit: int = 50) -> list[AiAuditEvent]:
        bounded_limit = max(1, min(limit, 500))
        with self._lock:
            events = [event.model_copy(deep=True) for event in self._events]
        indexed_events = enumerate(events)
        newest_first = sorted(
            indexed_events,
            key=lambda item: (item[1].created_at, item[0]),
            reverse=True,
        )
        return [event for _, event in newest_first[:bounded_limit]]

    def count_since(self, since: datetime) -> int:
        with self._lock:
            return sum(event.created_at >= since for event in self._events)
