"""Per-model rate-limit budget from the provider's `x-ratelimit-*` headers, for routing.

Groq sends, on every response (including 429s):
    x-ratelimit-limit-tokens / -remaining-tokens / -reset-tokens      (tokens per minute)
    x-ratelimit-limit-requests / -remaining-requests / -reset-requests (requests per day)
Input tokens are charged when a request is accepted, so the remaining-token count after a
response already includes it; the generated tokens are subtracted locally (`spend`).

Between observations the budget is projected forward with a linear refill: `reset-*` is the
time until the bucket is full again. A model is "near its limit" when the projected tokens do
not cover the next request's estimate (+ headroom) or no request is left; the router then
skips it BEFORE sending. Unknown budgets (no headers seen yet) count as available.
"""

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from app.core.limits import parse_duration


@dataclass
class _Bucket:
    limit: float | None = None
    remaining: float | None = None
    reset_seconds: float | None = None  # until full, measured at `observed_at`
    observed_at: float = 0.0

    def projected(self, now: float) -> float | None:
        if self.remaining is None:
            return None
        if self.limit is None or not self.reset_seconds:
            return self.remaining
        elapsed = max(0.0, now - self.observed_at)
        if elapsed >= self.reset_seconds:
            return self.limit
        missing = self.limit - self.remaining
        return self.remaining + missing * elapsed / self.reset_seconds

    def seconds_until(self, amount: float, now: float) -> float:
        """Time until the projected bucket holds `amount` (inf if it never will)."""
        current = self.projected(now)
        if current is None or current >= amount:
            return 0.0
        if self.limit is None or amount > self.limit or not self.reset_seconds:
            return float("inf")
        rate = (self.limit - (self.remaining or 0.0)) / self.reset_seconds
        return (amount - current) / rate if rate > 0 else float("inf")


@dataclass
class ModelBudget:
    tokens: _Bucket = field(default_factory=_Bucket)
    requests: _Bucket = field(default_factory=_Bucket)
    blocked_until: float = 0.0  # from a 429's Retry-After


@dataclass(frozen=True)
class Skip:
    model: str
    reason: str  # "TPM" | "RPD" | "429"
    wait_seconds: float


@dataclass(frozen=True)
class RouteDecision:
    """`models`: the ones to try, in order (empty = all predicted over their limits; then
    `wait_seconds` says when the first one frees up). `skipped`: models passed over."""

    models: list[str]
    skipped: list[Skip]
    wait_seconds: float | None = None


def _number(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


class RateLimitTracker:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._models: dict[str, ModelBudget] = {}

    def budget(self, model: str) -> ModelBudget:
        return self._models.setdefault(model, ModelBudget())

    def observe(self, model: str, headers: Mapping[str, str]) -> None:
        """Record the `x-ratelimit-*` headers of a response from `model` (if present)."""
        now = self._clock()
        budget = self.budget(model)
        for bucket, kind in ((budget.tokens, "tokens"), (budget.requests, "requests")):
            remaining = _number(headers.get(f"x-ratelimit-remaining-{kind}"))
            if remaining is None:
                continue
            bucket.remaining = remaining
            bucket.limit = _number(headers.get(f"x-ratelimit-limit-{kind}")) or bucket.limit
            bucket.reset_seconds = parse_duration(headers.get(f"x-ratelimit-reset-{kind}"))
            bucket.observed_at = now

    def spend(self, model: str, tokens: int) -> None:
        """Generated tokens count against TPM after the fact."""
        bucket = self.budget(model).tokens
        if bucket.remaining is not None and tokens > 0:
            now = self._clock()
            projected = bucket.projected(now)
            assert projected is not None
            # Re-anchor the projection at `now` so the refill continues from here.
            if bucket.reset_seconds and bucket.limit is not None:
                elapsed = max(0.0, now - bucket.observed_at)
                bucket.reset_seconds = max(0.0, bucket.reset_seconds - elapsed)
            bucket.remaining = max(0.0, projected - tokens)
            bucket.observed_at = now

    def block(self, model: str, retry_after: float | None) -> None:
        """A 429: the model is unavailable for `retry_after` seconds (default 10)."""
        self.budget(model).blocked_until = self._clock() + (retry_after or 10.0)

    def check(self, model: str, needed_tokens: int) -> Skip | None:
        """None if `model` can take a request of about `needed_tokens`, else why not."""
        now = self._clock()
        budget = self.budget(model)
        if now < budget.blocked_until:
            return Skip(model, "429", budget.blocked_until - now)
        requests = budget.requests.projected(now)
        if requests is not None and requests < 1:
            return Skip(model, "RPD", budget.requests.seconds_until(1, now))
        tokens = budget.tokens.projected(now)
        if tokens is not None and tokens < needed_tokens:
            return Skip(model, "TPM", budget.tokens.seconds_until(needed_tokens, now))
        return None

    def route(self, models: Sequence[str], needed_tokens: int) -> RouteDecision:
        """Keep the preference order, dropping models predicted to be over their limits."""
        usable: list[str] = []
        skipped: list[Skip] = []
        for model in models:
            if (skip := self.check(model, needed_tokens)) is None:
                usable.append(model)
            else:
                skipped.append(skip)
        if usable:
            return RouteDecision(usable, skipped)
        return RouteDecision([], skipped, min(skip.wait_seconds for skip in skipped))
