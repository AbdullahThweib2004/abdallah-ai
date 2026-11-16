"""System prompt assembly: the versioned rules plus a compact KNOWLEDGE section.

Until RAG (step 5) the whole approved knowledge base is small enough to send every time.
"""

import logging
from collections.abc import Sequence
from functools import cache
from pathlib import Path

from app.knowledge.loader import KnowledgeDocument
from app.knowledge.schemas import ContactMeta, ProjectMeta
from app.services.knowledge_service import visible_sections

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
PROMPT_VERSION = "v1"


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


def build_knowledge_section(
    documents: Sequence[KnowledgeDocument],
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
            lines.append(f"## {section.heading}\n{section.body_markdown}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_system_prompt(documents: Sequence[KnowledgeDocument]) -> str:
    knowledge = build_knowledge_section(documents)
    prompt = load_prompt_template().replace("{knowledge}", knowledge)
    logger.info(
        "System prompt %s built: knowledge ~%d tokens, total ~%d tokens (estimate)",
        PROMPT_VERSION,
        estimate_tokens(knowledge),
        estimate_tokens(prompt),
    )
    return prompt
