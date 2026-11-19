"""Action evals: does the model request the right card? (manual, real provider, costs tokens)

    cd backend && uv run python -m evals.run_actions [--model ID] [--only ID ...] [--limit N]

Same path as the app (retrieval → system prompt → stream), then the app's own ACTIONS parser
and allowlist. A case passes when the VALIDATED actions equal the expected set. Sequential and
quota-safe like run_chat (evals/quota.py): default model = the fallback (20b), early stop on a
daily limit or low remaining requests.
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.agents.actions import ActionPrefixParser, PrefixResult, dump_actions, split_actions
from app.core.config import get_settings
from app.llm.factory import build_provider
from app.services.language import detect_language
from evals.api_target import ApiTarget
from evals.quota import QuotaGuard, QuotaStop, add_quota_arguments, eval_settings, select_cases
from evals.run_chat import ask_with_backoff, build_context

CASES_FILE = Path(__file__).parent / "action_cases.yaml"


def label(action: dict[str, str]) -> str:
    return f"{action['type']}:{action['project_id']}" if "project_id" in action else action["type"]


def has_prefix(raw: str) -> bool:
    parser = ActionPrefixParser()
    fed = parser.feed(raw)
    result = fed if isinstance(fed, PrefixResult) else parser.finish()
    return isinstance(result, PrefixResult) and result.raw is not None


@dataclass
class Outcome:
    case_id: str
    language: str
    passed: bool
    expected: str
    got: str
    prefix: bool
    answer: str
    tokens: tuple[int, int]
    error: str | None = None


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_quota_arguments(parser)
    parser.add_argument("--api-url", help="evaluate a deployed site's /api/v1/chat instead")
    parser.add_argument("--lang", choices=["en", "ar"], help="run only cases in this language")
    parser.add_argument("--delay", type=float, default=2.0, help="seconds between cases")
    parser.add_argument("--show-answers", action="store_true", help="print every answer")
    args = parser.parse_args()

    settings = eval_settings(get_settings(), args.model)
    if settings.llm_provider == "fake":
        print("LLM_PROVIDER=fake: evals need the real provider configured in .env", file=sys.stderr)
        return 2
    context = build_context(settings)
    if context is None:
        print("Knowledge base failed to load", file=sys.stderr)
        return 2
    provider = ApiTarget(args.api_url) if args.api_url else build_provider(settings)

    cases = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        case["language"] = detect_language(case["message"], "en")
    cases = select_cases(cases, only=args.only, lang=args.lang, limit=args.limit)
    guard = QuotaGuard(args.max_wait, args.reserve_requests)

    print(f"Provider {provider.name}, model {provider.model}, {len(cases)} cases\n", flush=True)
    outcomes: list[Outcome] = []
    stopped: str | None = None
    try:
        for index, case in enumerate(cases):
            if index:
                await asyncio.sleep(args.delay)
            accepted = [sorted(option) for option in case.get("accept") or [case["expect"]]]
            expected = " | ".join(", ".join(option) or "[]" for option in accepted)
            reply = await ask_with_backoff(provider, context, case, settings, guard)
            if reply.error:
                outcome = Outcome(
                    case["id"], case["language"], False, expected, "-", False, "", (0, 0),
                    reply.error,
                )  # fmt: skip
            else:
                actions, answer = split_actions(reply.raw, context.project_ids)
                got = sorted(label(action) for action in dump_actions(actions))
                outcome = Outcome(
                    case["id"], case["language"], got in accepted, expected,
                    ", ".join(got) or "[]", has_prefix(reply.raw), answer,
                    (reply.usage.input_tokens, reply.usage.output_tokens),
                )  # fmt: skip
            outcomes.append(outcome)
            status = "PASS" if outcome.passed else "FAIL"
            print(f"  [{index + 1}/{len(cases)}] {status} {case['id']}", flush=True)
            if args.show_answers or not outcome.passed:
                print(f"      got {outcome.got}; answer: {outcome.answer[:160]!r}", flush=True)
            guard.check_remaining(provider)
    except QuotaStop as stop:
        stopped = f"STOPPED EARLY after {len(outcomes)}/{len(cases)} cases: {stop}"
        print(f"\n{stopped}", flush=True)
    finally:
        await provider.aclose()

    headers = ("CASE", "LANG", "RESULT", "EXPECTED", "GOT", "PREFIX")
    rows = [
        (o.case_id, o.language, "PASS" if o.passed else "FAIL", o.expected,
         o.error or o.got, "yes" if o.prefix else "NO")
        for o in outcomes
    ]  # fmt: skip
    widths = [max(len(row[i]) for row in [headers, *rows]) for i in range(len(headers))]
    print()
    for row in [headers, *rows]:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)))

    def rate(items: list[Outcome]) -> str:
        passed = sum(o.passed for o in items)
        return f"{passed}/{len(items)} = {passed / max(len(items), 1):.0%}"

    answered = [o for o in outcomes if o.tokens[0]]
    print(
        f"\nAccuracy: {rate(outcomes)} (EN {rate([o for o in outcomes if o.language == 'en'])}, "
        f"AR {rate([o for o in outcomes if o.language == 'ar'])})"
        f"\nACTIONS line present: {sum(o.prefix for o in outcomes)}/{len(outcomes)}"
        + (
            f"\nAvg tokens per question: {sum(o.tokens[0] for o in answered) // len(answered)} in"
            f" / {sum(o.tokens[1] for o in answered) // len(answered)} out"
            if answered
            else ""
        )
    )
    if isinstance(provider, ApiTarget):
        print(f"Served from the site's answer cache: {provider.cached}/{len(cases)}")
    if stopped:
        print(f"\n{stopped}")
        return 3
    passed = sum(o.passed for o in outcomes)
    return 0 if passed / max(len(outcomes), 1) >= 0.9 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
