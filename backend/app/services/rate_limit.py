"""Per-IP rate limits and a global daily cap.

In-memory for now (single process). Step 10 can swap in a shared store (e.g. Redis) behind
the same `RateLimiter` protocol.
"""

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

DAY_SECONDS = 86_400

Reason = Literal["rate_limited", "daily_limit", "daily_cap"]
# How each reason appears in `rate_limit source=app limit=...` log lines.
LIMIT_NAMES: dict[str, str] = {
    "rate_limited": "per_ip_minute",
    "daily_limit": "per_ip_day",
    "daily_cap": "global_day",
}


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    reason: Reason | None = None
    retry_after: int | None = None


class RateLimiter(Protocol):
    def check(self, key: str) -> RateDecision:
        """Decide for one request from `key` (an IP) and, if allowed, count it."""
        ...


class InMemoryRateLimiter:
    def __init__(
        self,
        *,
        per_minute: int,
        per_day: int,
        global_per_day: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._per_minute = per_minute
        self._per_day = per_day
        self._global_per_day = global_per_day
        self._clock = clock
        self._day = -1
        self._global_count = 0
        self._day_counts: dict[str, int] = {}
        self._recent: dict[str, deque[float]] = {}

    def check(self, key: str) -> RateDecision:
        now = self._clock()
        day = int(now // DAY_SECONDS)  # UTC day
        if day != self._day:
            self._day, self._global_count = day, 0
            self._day_counts.clear()
            self._recent.clear()
        until_tomorrow = int((day + 1) * DAY_SECONDS - now) + 1

        if self._global_count >= self._global_per_day:
            return RateDecision(False, "daily_cap", until_tomorrow)
        if self._day_counts.get(key, 0) >= self._per_day:
            return RateDecision(False, "daily_limit", until_tomorrow)

        recent = self._recent.setdefault(key, deque())
        while recent and recent[0] <= now - 60:
            recent.popleft()
        if len(recent) >= self._per_minute:
            return RateDecision(False, "rate_limited", int(60 - (now - recent[0])) + 1)

        recent.append(now)
        self._day_counts[key] = self._day_counts.get(key, 0) + 1
        self._global_count += 1
        return RateDecision(True)
