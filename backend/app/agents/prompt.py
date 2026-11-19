"""System prompt assembly: the versioned rules plus the KNOWLEDGE for one question.

Since step 5 the KNOWLEDGE section holds only the retrieved chunks (plus a small pinned
identity context), each labeled `[source: doc_id › heading]`. Since v5 the prompt also lists
the valid project ids for UI actions (`{project_catalog}`), built from the approved knowledge
base at startup.
"""

from collections.abc import Sequence
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.retriever import ScoredChunk

PROMPTS_DIR = Path(__file__).parent / "prompts"
PROMPT_VERSION = "v7"
IDENTITY_SOURCE = "about › Identity"


@cache
def load_prompt_template(version: str = PROMPT_VERSION) -> str:
    return (PROMPTS_DIR / f"system_{version}.md").read_text(encoding="utf-8")


def format_knowledge(identity: str, chunks: Sequence["ScoredChunk"]) -> str:
    blocks = [f"[source: {IDENTITY_SOURCE}]\n{identity}"] if identity else []
    blocks += [
        f"[source: {hit.chunk.doc_id} › {hit.chunk.heading}]\n{hit.chunk.text}" for hit in chunks
    ]
    if not chunks:
        blocks.append("(No passages matched this question.)")
    return "\n\n".join(blocks)


def format_project_catalog(projects: Sequence[tuple[str, str]]) -> str:
    """One `- <id>: <title>` line per approved project (the only ids actions may use)."""
    return "\n".join(f"- {project_id}: {title}" for project_id, title in projects) or "(none)"


def build_system_prompt(
    identity: str,
    chunks: Sequence["ScoredChunk"],
    projects: Sequence[tuple[str, str]] = (),
) -> str:
    """`projects` = (project_id, title) pairs. The KNOWLEDGE goes in last, so retrieved text
    can never expand the other placeholders."""
    return (
        load_prompt_template()
        .replace("{project_catalog}", format_project_catalog(projects))
        .replace("{example_project_id}", projects[0][0] if projects else "none")
        .replace("{knowledge}", format_knowledge(identity, chunks))
    )
