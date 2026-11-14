"""Load and validate the Markdown knowledge base.

Only documents with `status: approved` are ever served publicly; drafts are loaded only when
explicitly requested (e.g. by the validator CLI).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter
import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from app.knowledge.schemas import ContactMeta, KnowledgeMeta, knowledge_meta_adapter

TODO_PATTERN = re.compile(r"\bTODO\b")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

# Top-level folder -> the only document type allowed inside it.
FOLDER_TYPES: dict[str, str] = {
    "profile": "profile",
    "projects": "project",
    "career": "career",
    "contact": "contact",
    "glossary": "glossary",
}


class Section(BaseModel):
    model_config = ConfigDict(frozen=True)

    heading: str | None
    content: str

    @property
    def text(self) -> str:
        return f"## {self.heading}\n\n{self.content}" if self.heading else self.content


class KnowledgeDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    meta: KnowledgeMeta
    sections: list[Section]
    todo_count: int


@dataclass
class FileReport:
    path: str
    document: KnowledgeDocument | None
    todo_count: int
    errors: list[str] = field(default_factory=list)


class KnowledgeBaseError(Exception):
    def __init__(self, reports: list[FileReport]) -> None:
        self.reports = reports
        failing = [report for report in reports if report.errors]
        details = "; ".join(f"{r.path}: {', '.join(r.errors)}" for r in failing)
        super().__init__(f"{len(failing)} knowledge file(s) failed validation: {details}")


def split_sections(body: str) -> list[Section]:
    """Split a Markdown body into sections by `##` heading.

    HTML comments (authoring notes) are removed. Text before the first `##` is kept as a
    section without heading, minus any `#` title line. `##` inside fenced code is ignored.
    """
    sections: list[Section] = []
    heading: str | None = None
    lines: list[str] = []
    in_fence = False

    def flush() -> None:
        kept = lines if heading else [line for line in lines if not line.startswith("# ")]
        content = "\n".join(kept).strip()
        if heading or content:
            sections.append(Section(heading=heading, content=content))

    for line in HTML_COMMENT.sub("", body).splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            flush()
            heading, lines = line[3:].strip(), []
            continue
        lines.append(line)
    flush()
    return sections


def discover_files(root: Path) -> list[Path]:
    """Knowledge files: Markdown inside a subfolder, excluding READMEs and `_`-prefixed paths."""
    return sorted(path for path in root.rglob("*.md") if _is_knowledge_file(path.relative_to(root)))


def _is_knowledge_file(relative: Path) -> bool:
    return (
        len(relative.parts) > 1
        and relative.name != "README.md"
        and not any(part.startswith("_") for part in relative.parts)
    )


def _format_validation_error(exc: ValidationError) -> list[str]:
    messages = []
    for error in exc.errors():
        # Drop the discriminator tag that pydantic prepends to union locations.
        loc = [str(part) for part in error["loc"]]
        if loc and loc[0] in FOLDER_TYPES.values():
            loc = loc[1:]
        message = error["msg"].removeprefix("Value error, ")
        messages.append(f"{'.'.join(loc)}: {message}" if loc else message)
    return messages


def _load_file(root: Path, path: Path) -> FileReport:
    relative = path.relative_to(root)
    text = path.read_text(encoding="utf-8")
    report = FileReport(path=relative.as_posix(), document=None, todo_count=0)
    report.todo_count = len(TODO_PATTERN.findall(text))

    try:
        post = frontmatter.loads(text)
    except yaml.YAMLError as exc:
        report.errors.append(f"invalid YAML frontmatter: {exc}")
        return report
    if not post.metadata:
        report.errors.append("missing YAML frontmatter")
        return report

    try:
        meta = knowledge_meta_adapter.validate_python(post.metadata)
    except ValidationError as exc:
        report.errors.extend(_format_validation_error(exc))
        return report

    expected_type = FOLDER_TYPES.get(relative.parts[0])
    if expected_type is None:
        report.errors.append(f"unknown folder '{relative.parts[0]}'")
    elif meta.type != expected_type:
        report.errors.append(f"type '{meta.type}' not allowed in {relative.parts[0]}/")

    if meta.status == "approved" and report.todo_count:
        report.errors.append(
            f"status 'approved' but {report.todo_count} TODO placeholder(s) remain"
        )

    report.document = KnowledgeDocument(
        path=report.path,
        meta=meta,
        sections=split_sections(post.content),
        todo_count=report.todo_count,
    )
    return report


def _flag_duplicates(reports: list[FileReport], key: str, values: dict[str, list[str]]) -> None:
    for value, owners in values.items():
        if len(owners) > 1:
            for report in reports:
                if report.path in owners:
                    others = ", ".join(owner for owner in owners if owner != report.path)
                    report.errors.append(f"duplicate {key} '{value}' (also in {others})")


def validate_knowledge_base(root: Path) -> list[FileReport]:
    """Validate every knowledge file under `root` and return one report per file."""
    if not root.is_dir():
        raise FileNotFoundError(f"knowledge base directory not found: {root}")

    reports = [_load_file(root, path) for path in discover_files(root)]

    ids: dict[str, list[str]] = {}
    link_ids: dict[str, list[str]] = {}
    for report in reports:
        if report.document is None:
            continue
        meta = report.document.meta
        ids.setdefault(meta.id, []).append(report.path)
        if isinstance(meta, ContactMeta):
            for link in meta.links:
                link_ids.setdefault(link.link_id, []).append(report.path)

    _flag_duplicates(reports, "id", ids)
    # Duplicates within one file are already rejected by ContactMeta.
    _flag_duplicates(reports, "link_id", {k: sorted(set(v)) for k, v in link_ids.items()})
    return reports


def load_knowledge_base(root: Path, include_drafts: bool = False) -> list[KnowledgeDocument]:
    """Load the knowledge base, raising `KnowledgeBaseError` if any file is invalid.

    Drafts are excluded unless `include_drafts` is True. Only approved documents may be
    served publicly.
    """
    reports = validate_knowledge_base(root)
    if any(report.errors for report in reports):
        raise KnowledgeBaseError(reports)
    return [
        report.document
        for report in reports
        if report.document is not None
        and (include_drafts or report.document.meta.status == "approved")
    ]
