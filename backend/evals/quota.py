"""Quota-safe eval runs: the Groq daily quota is shared with the live site.

- `--model`: the model under test. Default: the FALLBACK model (gpt-oss-20b), so routine runs
  leave the main model's daily tokens to visitors. Pass the main model explicitly to evaluate it.
  The fallback is always off during evals: the named model is the one graded.
- `--limit N` / `--only id,id ...`: run a few cases instead of the whole set.
- Early stop instead of waiting for hours: a 429 on a DAILY limit (TPD/RPD, as reported in
  Groq's message, or the router predicting no requests left), a 429 whose Retry-After exceeds
  `--max-wait`, or fewer than `--reserve-requests` requests left today (from the
  `x-ratelimit-remaining-requests` header) ends the run with a clear message and the results
  gathered so far. Per-minute (TPM) limits still wait, up to `--max-wait`.
"""

import argparse
from dataclasses import dataclass

from app.llm.base import LLMProvider, LLMRateLimitError

DAILY_LIMITS = {"TPD", "RPD", "ASD"}
DEFAULT_MAX_WAIT_SECONDS = 90.0
DEFAULT_RESERVE_REQUESTS = 150  # of 1,000/day per model, kept for the live site


class QuotaStop(Exception):  # noqa: N818 - a stop signal, not an error
    """The run must end now; the message says why and what to do."""


def add_quota_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--model",
        help="model to evaluate (default: LLM_FALLBACK_MODEL, to spare the main model's quota)",
    )
    parser.add_argument("--only", nargs="+", help="case ids (space or comma separated)")
    parser.add_argument("--limit", type=int, help="run at most N cases (after the filters)")
    parser.add_argument(
        "--max-wait",
        type=float,
        default=DEFAULT_MAX_WAIT_SECONDS,
        help="longest 429 wait before stopping (seconds)",
    )
    parser.add_argument(
        "--reserve-requests",
        type=int,
        default=DEFAULT_RESERVE_REQUESTS,
        help="stop when fewer requests than this are left today for the model",
    )


def eval_settings(settings, model: str | None):
    """Settings for an eval run: one explicit model, no fallback."""
    chosen = model or settings.llm_fallback_model or settings.llm_model
    return settings.model_copy(update={"llm_model": chosen, "llm_fallback_model": None})


def select_cases(
    cases: list[dict],
    *,
    only: list[str] | None = None,
    lang: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Filter by ids (order of the case file), language, then the first `limit`."""
    if only:
        wanted = {part for item in only for part in item.split(",") if part}
        unknown = wanted - {case["id"] for case in cases}
        if unknown:
            raise SystemExit(f"Unknown case id(s): {', '.join(sorted(unknown))}")
        cases = [case for case in cases if case["id"] in wanted]
    if lang:
        cases = [case for case in cases if case.get("language", "en") == lang]
    if limit is not None:
        cases = cases[: max(limit, 0)]
    return cases


@dataclass
class QuotaGuard:
    max_wait: float = DEFAULT_MAX_WAIT_SECONDS
    reserve_requests: int = DEFAULT_RESERVE_REQUESTS

    def wait_for(self, error: LLMRateLimitError, model: str) -> float:
        """Seconds to wait before retrying, or raise `QuotaStop` for a daily/long limit."""
        if error.limit in DAILY_LIMITS:
            raise QuotaStop(
                f"{model}: daily quota reached ({error.limit}, Groq says retry in "
                f"{error.retry_after or '?'}s). Stopped so the live site keeps its quota; "
                "re-run later, or with --model <other> / --only / --limit."
            )
        wait = error.retry_after if error.retry_after is not None else 10.0
        if wait > self.max_wait:
            raise QuotaStop(
                f"{model}: rate limited ({error.limit or 'unknown'}) for {wait:.0f}s, longer "
                f"than --max-wait {self.max_wait:.0f}s. Stopped instead of waiting."
            )
        return wait

    def check_remaining(self, provider: LLMProvider) -> None:
        """Raise `QuotaStop` when the model has fewer than `reserve_requests` left today."""
        tracker = getattr(provider, "tracker", None)
        if tracker is None:
            return
        remaining = tracker.budget(provider.model).requests.remaining
        if remaining is not None and remaining < self.reserve_requests:
            raise QuotaStop(
                f"{provider.model}: only {remaining:.0f} requests left today (reserve "
                f"{self.reserve_requests} for the live site, --reserve-requests). Stopped."
            )
