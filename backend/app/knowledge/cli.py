"""Knowledge base command line tools.

Usage:
    uv run python -m app.knowledge.cli validate [--approved-only] [--root PATH]
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from app.core.config import get_settings
from app.knowledge.loader import FileReport, validate_knowledge_base

HEADERS = ("FILE", "ID", "TYPE", "STATUS", "TODOS", "ERRORS")


def _row(report: FileReport) -> tuple[str, ...]:
    meta = report.document.meta if report.document else None
    return (
        report.path,
        meta.id if meta else "-",
        meta.type if meta else "-",
        meta.status if meta else "-",
        str(report.todo_count),
        "; ".join(report.errors) if report.errors else "-",
    )


def _print_table(rows: list[tuple[str, ...]]) -> None:
    # The last column (errors) is not padded so long messages don't widen the table.
    widths = [max(len(row[i]) for row in [HEADERS, *rows]) for i in range(len(HEADERS) - 1)]
    for row in [HEADERS, *rows]:
        cells = [cell.ljust(width) for cell, width in zip(row, widths, strict=False)]
        print("  ".join([*cells, row[-1]]))


def validate(root: Path, approved_only: bool) -> int:
    reports = validate_knowledge_base(root)
    failing = [report for report in reports if report.errors]
    approved = [
        r for r in reports if r.document is not None and r.document.meta.status == "approved"
    ]

    print(f"Knowledge base: {root}\n")
    if approved_only:
        if approved:
            _print_table([_row(report) for report in approved])
        else:
            print("No approved documents. Nothing would be served publicly.")
        print(f"\n{len(approved)} of {len(reports)} document(s) approved (public).")
    else:
        _print_table([_row(report) for report in reports])
        drafts = [
            r for r in reports if r.document is not None and r.document.meta.status == "draft"
        ]
        total_todos = sum(report.todo_count for report in reports)
        print(
            f"\n{len(reports)} file(s): {len(approved)} approved, {len(drafts)} draft, "
            f"{total_todos} TODO(s)."
        )

    if failing:
        print(f"{len(failing)} file(s) with errors.", file=sys.stderr)
        return 1
    print("Validation passed.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.knowledge.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate_cmd = commands.add_parser("validate", help="validate every knowledge file")
    validate_cmd.add_argument(
        "--approved-only",
        action="store_true",
        help="list only documents that would currently be served publicly",
    )
    validate_cmd.add_argument(
        "--root", type=Path, default=None, help="knowledge base directory (default: settings)"
    )
    args = parser.parse_args(argv)

    root = (args.root or get_settings().knowledge_base_dir).resolve()
    return validate(root, approved_only=args.approved_only)


if __name__ == "__main__":
    sys.exit(main())
