"""System prompt assembly: the versioned rules plus the KNOWLEDGE for one question.

Since step 5 the KNOWLEDGE section holds only the retrieved chunks (plus a small pinned
identity context), each labeled `[source: doc_id › heading]`.
"""

from collections.abc import Sequence
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.retriever import ScoredChunk

PROMPTS_DIR = Path(__file__).parent / "prompts"
PROMPT_VERSION = "v3"
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


def build_system_prompt(identity: str, chunks: Sequence["ScoredChunk"]) -> str:
    return load_prompt_template().replace("{knowledge}", format_knowledge(identity, chunks))
