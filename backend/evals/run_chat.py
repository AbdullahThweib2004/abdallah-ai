"""Run the chat eval set against the REAL provider configured in `.env` (manual, not pytest).

    cd backend && uv run python -m evals.run_chat [--model ID] [--only ID ...] [--limit N]

Quota-safe (see evals/quota.py): the default model is the FALLBACK (20b), the fallback is
off so exactly that model is graded, per-minute 429s wait up to --max-wait, and a daily limit
or a low remaining-requests count stops the run early with the results so far.
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.agents.actions import split_actions
from app.agents.prompt import build_system_prompt
from app.core.config import get_settings
from app.llm.base import LLMProvider, LLMRateLimitError, Usage
from app.llm.factory import build_provider
from app.models.chat import ChatRequest, ChatTurn
from app.rag.identity import build_identity_context
from app.rag.retriever import Retriever
from app.rag.service import build_retriever
from app.services.answer_quality import answer_problems, normalize
from app.services.chat_service import build_messages, previous_user_message, reasoning_effort_for
from app.services.knowledge_service import load_knowledge_service
from app.services.language import detect_language
from evals.quota import QuotaGuard, QuotaStop, add_quota_arguments, eval_settings, select_cases

CASES_FILE = Path(__file__).parent / "chat_cases.yaml"
MAX_RATE_LIMIT_RETRIES = 6


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
    missing = [n for n in case.get("must_include_all") or [] if normalize(n) not in text]
    if missing:
        reasons.append(f"missing {', '.join(missing)}")
    for needle in case.get("must_not_include") or []:
        if normalize(needle) in text:
            reasons.append(f"contains forbidden {needle!r}")
    # Global rules (markdown, praise, Arabic mistakes, glued Latin, URLs, placeholders, the
    # name's spelling): shared with the answer cache, which never stores a failing answer.
    return reasons + answer_problems(answer)


@dataclass
class Context:
    retriever: Retriever
    identity: str
    # Approved (project_id, title) pairs: the prompt's action catalog and the allowlist.
    projects: list[tuple[str, str]] = field(default_factory=list)

    @property
    def project_ids(self) -> set[str]:
        return {project_id for project_id, _ in self.projects}


def build_context(settings) -> Context | None:
    knowledge = load_knowledge_service(settings.knowledge_base_dir)
    if knowledge is None:
        return None
    projects = knowledge.list_projects()
    return Context(
        build_retriever(knowledge.documents, settings),
        build_identity_context(knowledge.profile, knowledge.contact()),  # as in app/main.py
        [(project.id, project.title) for project in projects],
    )


async def ask(provider: LLMProvider, context: Context, case: dict, settings) -> tuple[str, Usage]:
    """Same path as the app: retrieve → prompt with retrieved chunks → stream the answer.

    Returns the RAW reply, including the model's `ACTIONS:` first line."""
    request = ChatRequest(
        message=case["message"],
        history=[ChatTurn(**turn) for turn in case.get("history", [])],
        ui_language=case.get("language", "en"),
    )
    language = detect_language(request.message, request.ui_language)
    retrieval = context.retriever.retrieve(request.message, previous_user_message(request))
    system_prompt = build_system_prompt(context.identity, retrieval.chunks, context.projects)
    messages = build_messages(system_prompt, request, language)
    parts: list[str] = []
    usage = Usage()
    async for chunk in provider.stream(
        messages,
        max_tokens=settings.llm_max_output_tokens,
        temperature=settings.llm_temperature,
        reasoning_effort=reasoning_effort_for(language, settings),
    ):
        parts.append(chunk.text)
        usage = chunk.usage or usage
    return "".join(parts), usage


@dataclass
class Reply:
    raw: str = ""
    usage: Usage = field(default_factory=Usage)
    latency_ms: int = 0
    rate_limit_hits: int = 0
    error: str | None = None


async def ask_with_backoff(
    provider: LLMProvider, context: Context, case: dict, settings, guard: QuotaGuard | None = None
) -> Reply:
    """`ask` with retries: a per-minute 429 waits (Retry-After) and tries again; a daily limit
    or a long wait raises `QuotaStop` (from the guard) instead of waiting for hours."""
    guard = guard or QuotaGuard()
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        started = time.perf_counter()
        try:
            raw, usage = await asyncio.wait_for(
                ask(provider, context, case, settings),
                timeout=settings.llm_timeout_seconds * 3,
            )
        except LLMRateLimitError as exc:
            wait = guard.wait_for(exc, provider.model)
            if attempt == MAX_RATE_LIMIT_RETRIES:
                return Reply(rate_limit_hits=attempt + 1, error="rate limited (gave up)")
            print(f"    429 on {case['id']}: waiting {wait:.0f}s (retry {attempt + 1})", flush=True)
            await asyncio.sleep(wait)
            continue
        except Exception as exc:  # noqa: BLE001 - report any provider failure as a failed case
            return Reply(error=f"error: {type(exc).__name__}: {exc}")
        latency = round((time.perf_counter() - started) * 1000)
        return Reply(raw, usage, latency, attempt)
    raise AssertionError("unreachable")


async def run_case(
    provider: LLMProvider, context: Context, case: dict, settings, guard: QuotaGuard
) -> Result:
    reply = await ask_with_backoff(provider, context, case, settings, guard)
    if reply.error:
        return Result(case["id"], False, [reply.error], rate_limit_hits=reply.rate_limit_hits)
    # Grade the answer the visitor sees: the model's raw text minus the ACTIONS line (which
    # the app never shows). No display fixes (such as Arabic/Latin spacing) are applied.
    _, answer = split_actions(reply.raw, context.project_ids)
    reasons = check(case, answer)
    return Result(
        case["id"], not reasons, reasons, reply.usage, reply.latency_ms, answer,
        reply.rate_limit_hits,
    )  # fmt: skip


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
    add_quota_arguments(parser)
    parser.add_argument("--delay", type=float, default=2.0, help="seconds between cases")
    parser.add_argument("--show-answers", action="store_true", help="print every answer")
    parser.add_argument("--lang", choices=["en", "ar"], help="run only cases in this language")
    parser.add_argument(
        "--reasoning-effort-ar",
        choices=["low", "medium", "high"],
        help="override for Arabic replies",
    )
    parser.add_argument("--json", type=Path, help="also write results (with answers) to this file")
    args = parser.parse_args()

    settings = eval_settings(get_settings(), args.model)
    if args.reasoning_effort_ar:
        settings = settings.model_copy(update={"llm_reasoning_effort_ar": args.reasoning_effort_ar})
    if settings.llm_provider == "fake":
        print("LLM_PROVIDER=fake: evals need the real provider configured in .env", file=sys.stderr)
        return 2

    context = build_context(settings)
    if context is None:
        print("Knowledge base failed to load", file=sys.stderr)
        return 2
    provider = build_provider(settings)

    cases = select_cases(
        yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))["cases"],
        only=args.only,
        lang=args.lang,
        limit=args.limit,
    )
    guard = QuotaGuard(args.max_wait, args.reserve_requests)

    print(
        f"Provider {provider.name}, model {provider.model}, {len(cases)} cases, retrieval "
        f"{'hybrid' if context.retriever.vector_enabled else 'BM25 only'} "
        f"(top {settings.rag_top_k}, budget {settings.rag_max_context_tokens} tokens), reasoning "
        f"{settings.llm_reasoning_effort} / Arabic {settings.llm_reasoning_effort_ar or 'same'}\n",
        flush=True,
    )
    results: list[Result] = []
    stopped: str | None = None
    try:
        for index, case in enumerate(cases):
            if index:
                await asyncio.sleep(args.delay)
            result = await run_case(provider, context, case, settings, guard)
            results.append(result)
            status = "PASS" if result.passed else "FAIL"
            print(f"  [{index + 1}/{len(cases)}] {status} {case['id']}", flush=True)
            if args.show_answers or not result.passed:
                print(f"      answer: {result.answer!r}", flush=True)
            guard.check_remaining(provider)
    except QuotaStop as stop:
        stopped = f"STOPPED EARLY after {len(results)}/{len(cases)} cases: {stop}"
        print(f"\n{stopped}", flush=True)
    finally:
        await provider.aclose()

    print()
    print_table(results)
    if args.json:
        args.json.write_text(
            json.dumps(
                [
                    {
                        "id": r.case_id,
                        "passed": r.passed,
                        "reasons": r.reasons,
                        "answer": r.answer,
                        "input_tokens": r.usage.input_tokens,
                        "output_tokens": r.usage.output_tokens,
                        "latency_ms": r.latency_ms,
                    }
                    for r in results
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
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
    if stopped:
        print(f"\n{stopped}")
        return 3
    return 0 if passed / max(len(results), 1) >= 0.9 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
