import pytest

from advisory.rate_limit import RateLimitExceededError, SlidingWindowRateLimiter


def test_sliding_window_blocks_burst_and_recovers() -> None:
    limiter = SlidingWindowRateLimiter(window_seconds=60)
    limiter.check("user", 2, now=0)
    limiter.check("user", 2, now=1)
    with pytest.raises(RateLimitExceededError):
        limiter.check("user", 2, now=2)
    limiter.check("user", 2, now=61)


def test_rate_limits_are_isolated_by_key() -> None:
    limiter = SlidingWindowRateLimiter()
    limiter.check("alice", 1, now=1)
    limiter.check("bob", 1, now=1)
    with pytest.raises(RateLimitExceededError):
        limiter.check("alice", 1, now=2)
