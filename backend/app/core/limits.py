"""One log line per rate-limit event, with its source and limit type (never visitor text).

    rate_limit source=groq model=openai/gpt-oss-120b limit=TPM retry_after=7.5
    rate_limit source=app limit=per_ip_minute route=chat retry_after=42

Sources: `groq` (chat), `groq-audio` (Whisper), `elevenlabs`, `app` (our own per-IP limits,
global daily caps and the TTS character budget) and `router` (a request the limit-aware router
did not send because every model was predicted to be over its limit).
"""

import logging
import re

logger = logging.getLogger("app.limits")

# Groq names the exhausted limit in the 429 message: "... on tokens per minute (TPM): ...".
# Only this short code is kept; the message itself (it names the organization) is never logged.
_GROQ_LIMIT = re.compile(r"\((TPM|RPM|TPD|RPD|ASH|ASD)\)")
_DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")
_UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


def log_rate_limit(
    source: str,
    limit: str,
    *,
    model: str | None = None,
    route: str | None = None,
    retry_after: float | None = None,
) -> None:
    parts = [f"source={source}"]
    if model:
        parts.append(f"model={model}")
    parts.append(f"limit={limit}")
    if route:
        parts.append(f"route={route}")
    if retry_after is not None:
        parts.append(f"retry_after={retry_after:g}")
    logger.warning("rate_limit %s", " ".join(parts))


def groq_limit_type(body: bytes | str | None) -> str:
    """`TPM`, `RPD`, ... from a Groq 429 body, or `unknown`."""
    if not body:
        return "unknown"
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    match = _GROQ_LIMIT.search(text)
    return match.group(1) if match else "unknown"


def parse_duration(value: str | None) -> float | None:
    """Groq reset headers: "547ms", "7.66s", "2m59.56s", "2h38m24s" → seconds. A bare number
    (as in Retry-After) is seconds."""
    if not value:
        return None
    value = value.strip()
    try:
        return float(value)
    except ValueError:
        pass
    parts = _DURATION_PART.findall(value)
    if not parts or "".join(number + unit for number, unit in parts) != value:
        return None
    return sum(float(number) * _UNIT_SECONDS[unit] for number, unit in parts)
