"""Run the chat eval set against the REAL provider configured in `.env` (manual, not pytest).

    cd backend && uv run python -m evals.run_chat [--only ID ...] [--allow-fallback]

Cases run sequentially. A 429 waits (Retry-After or exponential backoff) and retries, so
the run survives Groq's free-tier rate limits. The fallback model is disabled by default so
the main model is what gets evaluated.
"""

import argparse
import asyncio
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.agents.prompt import build_system_prompt, estimate_tokens
from app.core.config import get_settings
from app.llm.base import LLMProvider, LLMRateLimitError, Usage
from app.llm.factory import build_provider
from app.models.chat import ChatRequest, ChatTurn
from app.services.chat_service import build_messages
from app.services.knowledge_service import load_knowledge_service
from app.services.language import detect_language

CASES_FILE = Path(__file__).parent / "chat_cases.yaml"
MAX_RATE_LIMIT_RETRIES = 6
_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670\u0640]")
_HYPHENS = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2212]")
_SPACES = re.compile(r"[\u00A0\u202F\u2009\u200A]")
# Answers are shown as subtitles and spoken later: no markdown of any kind (prompt rule).
_MARKDOWN = re.compile(
    r"\*\*|__|```|^\s*#{1,6}\s|^\s*[-*•]\s|^\s*\d+\.\s|^\s*\|.*\|\s*$", re.MULTILINE
)


def normalize(text: str) -> str:
    text = _SPACES.sub(" ", _HYPHENS.sub("-", _DIACRITICS.sub("", text)))
    return text.casefold().replace("’", "'")


@dataclass
class Result:
    case_id: str
    passed: bool
    reasons: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    latency_ms: int = 0
    answer: str = ""
    rate_limit_hits: int = 0


def check(case: dict, answer: str) -> list[str]:
    reasons = []
    text = normalize(answer)
    if not answer.strip():
        return ["empty answer"]
    expected_language = case.get("language")
    if expected_language and detect_language(answer, expected_language) != expected_language:
        reasons.append(f"language is not {expected_language}")
    include = case.get("must_include_any") or []
    if include and not any(normalize(needle) in text for needle in include):
        reasons.append("missing all of must_include_any")
    for needle in case.get("must_not_include") or []:
        if normalize(needle) in text:
            reasons.append(f"contains forbidden {needle!r}")
    if _MARKDOWN.search(answer):
        reasons.append("uses markdown")
    return reasons


async def ask(provider: LLMProvider, system_prompt: str, case: dict, settings) -> tuple[str, Usage]:
    request = ChatRequest(
        message=case["message"],
        history=[ChatTurn(**turn) for turn in case.get("history", [])],
        ui_language=case.get("language", "en"),
    )
    language = detect_language(request.message, request.ui_language)
    messages = build_messages(system_prompt, request, language)
    parts: list[str] = []
    usage = Usage()
    async for chunk in provider.stream(
        messages, max_tokens=settings.llm_max_output_tokens, temperature=settings.llm_temperature
    ):
        parts.append(chunk.text)
        usage = chunk.usage or usage
    return "".join(parts), usage


async def run_case(provider: LLMProvider, system_prompt: str, case: dict, settings) -> Result:
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        started = time.perf_counter()
        try:
            answer, usage = await asyncio.wait_for(
                ask(provider, system_prompt, case, settings),
                timeout=settings.llm_timeout_seconds * 3,
            )
        except LLMRateLimitError as exc:
            if attempt == MAX_RATE_LIMIT_RETRIES:
                return Result(
                    case["id"], False, ["rate limited (gave up)"], rate_limit_hits=attempt + 1
                )
            wait = exc.retry_after or min(60, 5 * 2**attempt)
            print(f"    429 on {case['id']}: waiting {wait:.0f}s (retry {attempt + 1})", flush=True)
            await asyncio.sleep(wait)
            continue
        except Exception as exc:  # noqa: BLE001 - report any provider failure as a failed case
            return Result(case["id"], False, [f"error: {type(exc).__name__}: {exc}"])
        latency = round((time.perf_counter() - started) * 1000)
        reasons = check(case, answer)
        return Result(case["id"], not reasons, reasons, usage, latency, answer, attempt)
    raise AssertionError("unreachable")


def print_table(results: list[Result]) -> None:
    rows = [
        (
            r.case_id,
            "PASS" if r.passed else "FAIL",
            "; ".join(r.reasons) or "-",
            f"{r.usage.input_tokens}/{r.usage.output_tokens}",
            str(r.latency_ms),
        )
        for r in results
    ]
    headers = ("CASE", "RESULT", "REASON", "TOKENS in/out", "LATENCY ms")
    widths = [max(len(row[i]) for row in [headers, *rows]) for i in range(len(headers))]
    for row in [headers, *rows]:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="run only these case ids")
    parser.add_argument("--allow-fallback", action="store_true", help="keep LLM_FALLBACK_MODEL on")
    parser.add_argument("--delay", type=float, default=2.0, help="seconds between cases")
    parser.add_argument("--show-answers", action="store_true", help="print every answer")
    args = parser.parse_args()

    settings = get_settings()
    if not args.allow_fallback:
        settings = settings.model_copy(update={"llm_fallback_model": None})
    if settings.llm_provider == "fake":
        print("LLM_PROVIDER=fake: evals need the real provider configured in .env", file=sys.stderr)
        return 2

    knowledge = load_knowledge_service(settings.knowledge_base_dir)
    if knowledge is None:
        print("Knowledge base failed to load", file=sys.stderr)
        return 2
    system_prompt = build_system_prompt(knowledge.documents, settings.llm_knowledge_mode)
    provider = build_provider(settings)

    cases = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))["cases"]
    if args.only:
        cases = [case for case in cases if case["id"] in args.only]

    print(
        f"Provider {provider.name}, model {provider.model}, {len(cases)} cases, "
        f"knowledge mode {settings.llm_knowledge_mode}, "
        f"system prompt ~{estimate_tokens(system_prompt)} tokens (estimate)\n",
        flush=True,
    )
    results: list[Result] = []
    try:
        for index, case in enumerate(cases):
            if index:
                await asyncio.sleep(args.delay)
            result = await run_case(provider, system_prompt, case, settings)
            results.append(result)
            status = "PASS" if result.passed else "FAIL"
            print(f"  [{index + 1}/{len(cases)}] {status} {case['id']}", flush=True)
            if args.show_answers or not result.passed:
                print(f"      answer: {result.answer!r}", flush=True)
    finally:
        await provider.aclose()

    print()
    print_table(results)
    passed = sum(r.passed for r in results)
    answered = [r for r in results if r.usage.input_tokens]
    total_in = sum(r.usage.input_tokens for r in results)
    total_out = sum(r.usage.output_tokens for r in results)
    cost = (
        total_in * settings.llm_input_cost_per_mtok + total_out * settings.llm_output_cost_per_mtok
    ) / 1_000_000
    print(
        f"\nPass rate: {passed}/{len(results)} = {passed / max(len(results), 1):.0%}"
        f"\nRate limits: {sum(1 for r in results if r.rate_limit_hits)} case(s) hit 429, "
        f"{sum(r.rate_limit_hits for r in results)} retry wait(s) in total"
        f"\nTokens: {total_in} in / {total_out} out"
        + (
            f" (avg {total_in // len(answered)} in / {total_out // len(answered)} out per question)"
            if answered
            else ""
        )
        + f"\nEstimated cost: ${cost:.4f} total"
        + (f", ${cost / len(answered):.5f} per question" if answered else "")
        + (
            ""
            if settings.llm_input_cost_per_mtok or settings.llm_output_cost_per_mtok
            else "  (set LLM_INPUT_COST_PER_MTOK / LLM_OUTPUT_COST_PER_MTOK for a real estimate)"
        )
    )
    return 0 if passed / max(len(results), 1) >= 0.9 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
