from __future__ import annotations

from collections import defaultdict, deque
from threading import RLock
from time import monotonic


class RateLimitExceededError(RuntimeError):
    pass


class SlidingWindowRateLimiter:
    """Small per-instance burst guard; durable monthly ledgers remain the cost authority."""

    def __init__(self, window_seconds: float = 60.0) -> None:
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = RLock()

    def check(self, key: str, limit: int, *, now: float | None = None) -> None:
        current = monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= limit:
                raise RateLimitExceededError("AI request limit reached; wait a minute and try again")
            attempts.append(current)

    def clear(self) -> None:
        with self._lock:
            self._attempts.clear()
