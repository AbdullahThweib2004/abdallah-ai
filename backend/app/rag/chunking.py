"""Split approved knowledge documents into retrieval chunks.

One chunk per `##` section; sections longer than `MAX_WORDS` are split into overlapping
windows. Every chunk starts with "{title} — {heading}" so it carries its own context.
Project and contact frontmatter (status, technologies, links) becomes one extra chunk.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.knowledge.loader import KnowledgeDocument
from app.knowledge.schemas import ContactMeta, GlossaryMeta, ProjectMeta
from app.services.knowledge_service import visible_sections

MAX_WORDS = 350
OVERLAP_WORDS = 50
CHUNKER_VERSION = "2"  # bump when chunking changes so indexes rebuild

# Sections that are UI copy, not knowledge. The greeting is mostly Arabic/English sample text
# and would otherwise match almost any Arabic query on script alone.
NOT_INDEXED: set[tuple[str, str]] = {("about", "Short self-introduction")}


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    doc_id: str
    type: str
    title: str
    heading: str
    project_id: str | None
    language: str
    index: int  # position of the chunk within its document

    def metadata(self) -> dict[str, str | int]:
        data: dict[str, str | int] = {
            "doc_id": self.doc_id,
            "type": self.type,
            "title": self.title,
            "heading": self.heading,
            "language": self.language,
            "chunk_index": self.index,
        }
        if self.project_id:
            data["project_id"] = self.project_id
        return data


def metadata_lines(document: KnowledgeDocument) -> list[str]:
    """Facts that live in frontmatter rather than in a section."""
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


def split_words(text: str, max_words: int = MAX_WORDS, overlap: int = OVERLAP_WORDS) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text]
    step = max_words - overlap
    return [
        " ".join(words[start : start + max_words]) for start in range(0, len(words) - overlap, step)
    ]


def chunk_documents(documents: Sequence[KnowledgeDocument]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for document in documents:
        meta = document.meta
        # Only approved content is ever indexed. The glossary is used for query expansion,
        # not as an answer source.
        if meta.status != "approved" or isinstance(meta, GlossaryMeta):
            continue
        project_id = meta.id if isinstance(meta, ProjectMeta) else None

        sections: list[tuple[str, str]] = []
        if extra := metadata_lines(document):
            heading = "Project facts" if project_id else "Links"
            sections.append((heading, "\n".join(extra)))
        sections += [
            (s.heading, s.body_markdown)
            for s in visible_sections(document)
            if (meta.id, s.heading) not in NOT_INDEXED
        ]

        for heading, body in sections:
            for part, piece in enumerate(split_words(body)):
                index = len([c for c in chunks if c.doc_id == meta.id])
                chunks.append(
                    Chunk(
                        id=f"{meta.id}::{index}" + (f"::{part}" if part else ""),
                        text=f"{meta.title} — {heading}\n{piece}",
                        doc_id=meta.id,
                        type=meta.type,
                        title=meta.title,
                        heading=heading,
                        project_id=project_id,
                        language=meta.language,
                        index=index,
                    )
                )
    return chunks
