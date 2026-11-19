"""Per-IP rate limits and a global daily cap.

`InMemoryRateLimiter` serves one process (local dev, tests). `RedisRateLimiter` keeps the
counters in Upstash Redis, shared by every serverless instance: one atomic Lua script per
request (sliding 60 s window per IP, per-IP and global counters per UTC day). IPs are hashed
before they become keys. If Redis is unreachable it falls back to an in-memory limiter (per
instance) and logs it, instead of failing open or closed.
"""

import hashlib
import logging
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from app.core.redis import RedisError, UpstashRedis

logger = logging.getLogger(__name__)

DAY_SECONDS = 86_400

Reason = Literal["rate_limited", "daily_limit", "daily_cap"]
# How each reason appears in `rate_limit source=... limit=...` log lines.
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
    async def check(self, key: str) -> RateDecision:
        """Decide for one request from `key` (an IP) and, if allowed, count it."""
        ...


def hash_key(key: str) -> str:
    """Stored keys never contain a raw IP address."""
    return hashlib.sha256(f"abdallah-ai|{key}".encode()).hexdigest()[:20]


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

    async def check(self, key: str) -> RateDecision:
        return self.check_now(key)

    def check_now(self, key: str) -> RateDecision:
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


# KEYS: global day counter, IP day counter, IP recent-requests sorted set.
# ARGV: now (ms), per_minute, per_day, global_per_day, seconds until tomorrow, unique member.
_CHECK_SCRIPT = """
local now = tonumber(ARGV[1])
local ttl = tonumber(ARGV[5]) + 60
if tonumber(redis.call('GET', KEYS[1]) or '0') >= tonumber(ARGV[4]) then
  return {0, 'daily_cap', tonumber(ARGV[5])}
end
if tonumber(redis.call('GET', KEYS[2]) or '0') >= tonumber(ARGV[3]) then
  return {0, 'daily_limit', tonumber(ARGV[5])}
end
redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', now - 60000)
if redis.call('ZCARD', KEYS[3]) >= tonumber(ARGV[2]) then
  local oldest = redis.call('ZRANGE', KEYS[3], 0, 0, 'WITHSCORES')
  return {0, 'rate_limited', math.floor((60000 - (now - tonumber(oldest[2]))) / 1000) + 1}
end
redis.call('ZADD', KEYS[3], now, ARGV[6])
redis.call('PEXPIRE', KEYS[3], 61000)
redis.call('INCR', KEYS[2])
redis.call('EXPIRE', KEYS[2], ttl)
redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ttl)
return {1, '', 0}
"""


class RedisRateLimiter:
    def __init__(
        self,
        redis: UpstashRedis,
        *,
        name: str,
        scope: str,
        per_minute: int,
        per_day: int,
        global_per_day: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._redis = redis
        self._prefix = f"aa:{scope}:rl:{name}"
        self._limits = (per_minute, per_day, global_per_day)
        self._clock = clock
        self._fallback = InMemoryRateLimiter(
            per_minute=per_minute, per_day=per_day, global_per_day=global_per_day, clock=clock
        )

    async def check(self, key: str) -> RateDecision:
        now = self._clock()
        day = int(now // DAY_SECONDS)
        until_tomorrow = int((day + 1) * DAY_SECONDS - now) + 1
        ip = hash_key(key)
        keys = [
            f"{self._prefix}:global:{day}",
            f"{self._prefix}:day:{day}:{ip}",
            f"{self._prefix}:recent:{ip}",
        ]
        per_minute, per_day, global_per_day = self._limits
        args = [
            int(now * 1000), per_minute, per_day, global_per_day, until_tomorrow,
            uuid.uuid4().hex,
        ]  # fmt: skip
        try:
            allowed, reason, retry_after = await self._redis.eval(_CHECK_SCRIPT, keys, args)
        except (RedisError, ValueError, TypeError) as exc:
            logger.warning("Rate limiter: Redis unavailable (%s); in-memory fallback", exc)
            return self._fallback.check_now(key)
        if int(allowed):
            return RateDecision(True)
        return RateDecision(False, reason, int(retry_after))
