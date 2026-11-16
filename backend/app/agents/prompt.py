"""System prompt assembly: the versioned rules plus a compact KNOWLEDGE section.

Until RAG (step 5) the whole approved knowledge base is small enough to send every time.
"""

import logging
from collections.abc import Sequence
from functools import cache
from pathlib import Path
from typing import Literal

from app.knowledge.loader import KnowledgeDocument
from app.knowledge.schemas import ContactMeta, GlossaryMeta, ProjectMeta
from app.services.knowledge_service import visible_sections

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
PROMPT_VERSION = "v2"

KnowledgeMode = Literal["full", "compact"]

# --- TEMPORARY: `compact` knowledge mode, removed in step 5 when RAG arrives. -------------
# Keeps profile, experience, education, career and contact; for projects only the summary,
# contribution, key details and verified results; keeps only the glossary's names table and
# drops long skill lists.
COMPACT_PROJECT_SECTIONS = {
    "Status",
    "One-line summary",
    "Abdallah's contribution",
    "Key implementation details",
    "Results (only verified results)",
}
COMPACT_SKILL_SECTIONS = {"Programming languages", "AI and LLM engineering"}
# The names table keeps Arabic spellings of names; without it the model transliterates them.
COMPACT_GLOSSARY_SECTIONS = {"Names and places"}
# Long bullet lists are cut to their first bullets (the headline features come first).
COMPACT_TRIMMED_SECTIONS = {"Key implementation details": 3}
COMPACT_DROPPED_SECTIONS = {("about", "Short self-introduction")}


@cache
def load_prompt_template(version: str = PROMPT_VERSION) -> str:
    return (PROMPTS_DIR / f"system_{version}.md").read_text(encoding="utf-8")


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 characters per token); real counts come from provider usage."""
    return max(1, round(len(text) / 4))


def _metadata_lines(document: KnowledgeDocument) -> list[str]:
    meta = document.meta
    if isinstance(meta, ProjectMeta):
        lines = []
        if meta.project_status:
            lines.append(f"Status: {meta.project_status.replace('_', ' ')}")
        if meta.technologies:
            lines.append(f"Technologies: {', '.join(meta.technologies)}")
        if meta.repository_url:
            lines.append(f"Public repository: {meta.repository_url}")
        if meta.demo_url:
            lines.append(f"Demo: {meta.demo_url}")
        return lines
    if isinstance(meta, ContactMeta):
        return [
            f"{link.label}: {link.url.removeprefix('mailto:')}" for link in meta.links if link.url
        ]
    return []


def _keep_section(document: KnowledgeDocument, heading: str, mode: KnowledgeMode) -> bool:
    if mode == "full":
        return True
    if isinstance(document.meta, ProjectMeta):
        return heading in COMPACT_PROJECT_SECTIONS
    if isinstance(document.meta, GlossaryMeta):
        return heading in COMPACT_GLOSSARY_SECTIONS
    if document.meta.id == "skills":
        return heading in COMPACT_SKILL_SECTIONS
    return (document.meta.id, heading) not in COMPACT_DROPPED_SECTIONS


def _trim_bullets(body: str, keep: int) -> str:
    lines, bullets = [], 0
    for line in body.splitlines():
        if line.lstrip().startswith("- "):
            bullets += 1
            if bullets > keep:
                continue
        lines.append(line)
    return "\n".join(lines)


def build_knowledge_section(
    documents: Sequence[KnowledgeDocument], mode: KnowledgeMode = "full"
) -> str:
    """Compact text of APPROVED documents only.

    Each document becomes `[doc_id] Title`, its metadata lines, then `## heading` + text.
    """
    blocks = []
    for document in documents:
        if document.meta.status != "approved":
            continue
        lines = [f"[{document.meta.id}] {document.meta.title}", *_metadata_lines(document)]
        for section in visible_sections(document):
            if not _keep_section(document, section.heading, mode):
                continue
            body = section.body_markdown
            if mode == "compact" and section.heading in COMPACT_TRIMMED_SECTIONS:
                body = _trim_bullets(body, COMPACT_TRIMMED_SECTIONS[section.heading])
            lines.append(f"## {section.heading}\n{body}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_system_prompt(
    documents: Sequence[KnowledgeDocument], mode: KnowledgeMode = "full"
) -> str:
    knowledge = build_knowledge_section(documents, mode)
    prompt = load_prompt_template().replace("{knowledge}", knowledge)
    logger.info(
        "System prompt %s built (%s knowledge): knowledge ~%d tokens, total ~%d tokens (estimate)",
        PROMPT_VERSION,
        mode,
        estimate_tokens(knowledge),
        estimate_tokens(prompt),
    )
    return prompt
