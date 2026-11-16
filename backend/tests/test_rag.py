"""Retrieval pipeline with the offline FakeEmbedder (no model downloads, no network)."""

from pathlib import Path

import pytest

from app.core.tokens import estimate_tokens
from app.knowledge.loader import load_knowledge_base
from app.models.content import ContactLinkResponse, ContactResponse
from app.rag.chunking import MAX_WORDS, OVERLAP_WORDS, chunk_documents, split_words
from app.rag.embeddings import FakeEmbedder
from app.rag.identity import MAX_IDENTITY_TOKENS, build_identity_context
from app.rag.index import KnowledgeIndex
from app.rag.query_expansion import expand_query, glossary_terms
from app.rag.retriever import Retriever, ranks_from_scores, reciprocal_rank_fusion
from app.services.knowledge_service import KnowledgeService


@pytest.fixture
def documents(fixture_kb: Path):
    return load_knowledge_base(fixture_kb, include_drafts=True)


def make_retriever(documents, tmp_path: Path, **options) -> Retriever:
    chunks = chunk_documents(documents)
    index = KnowledgeIndex(tmp_path / "index", FakeEmbedder())
    index.ensure(chunks)
    return Retriever(
        chunks, index=index, embedder=FakeEmbedder(), glossary=glossary_terms(documents), **options
    )


# --- chunking --------------------------------------------------------------------------------


def test_only_approved_documents_are_chunked_and_glossary_is_not(documents) -> None:
    chunks = chunk_documents(documents)
    doc_ids = {chunk.doc_id for chunk in chunks}

    assert "secret-draft" not in doc_ids  # draft project
    assert "terms-ar-en" not in doc_ids  # glossary: used for query expansion only
    assert {"about", "alpha", "beta", "gamma", "public-links"} <= doc_ids


def test_chunks_start_with_title_and_heading_and_drop_frontmatter_pointers(documents) -> None:
    chunks = chunk_documents(documents)
    problem = next(c for c in chunks if c.doc_id == "alpha" and c.heading == "Problem")
    facts = next(c for c in chunks if c.doc_id == "alpha" and c.heading == "Project facts")

    assert problem.text == "Alpha — Problem\nA **real** problem."
    assert problem.metadata() == {
        "doc_id": "alpha",
        "type": "project",
        "title": "Alpha",
        "heading": "Problem",
        "language": "en",
        "chunk_index": problem.index,
        "project_id": "alpha",
    }
    assert "Technologies: Python, FastAPI" in facts.text
    assert not any(
        c.heading in {"Project ID", "Technologies"} for c in chunks
    )  # "See frontmatter."
    assert all("See frontmatter" not in c.text for c in chunks)


def test_long_sections_are_split_with_overlap() -> None:
    words = [f"w{i}" for i in range(800)]

    pieces = [piece.split() for piece in split_words(" ".join(words))]

    assert all(len(piece) <= MAX_WORDS for piece in pieces)
    assert pieces[0][-OVERLAP_WORDS:] == pieces[1][:OVERLAP_WORDS]  # windows overlap
    assert pieces[-1][-1] == "w799"  # nothing lost at the end
    assert split_words("short text") == ["short text"]


# --- index -----------------------------------------------------------------------------------


def test_index_rebuilds_only_when_content_changes(documents, tmp_path: Path) -> None:
    chunks = chunk_documents(documents)
    index = KnowledgeIndex(tmp_path / "index", FakeEmbedder())

    assert index.ensure(chunks) is True  # first build
    assert index.ensure(chunks) is False  # unchanged: reused
    reopened = KnowledgeIndex(tmp_path / "index", FakeEmbedder())
    assert reopened.ensure(chunks) is False  # survives a restart
    assert reopened.ensure(chunks[:-1]) is True  # content changed: rebuilt
    assert reopened.stats()["chunks"] == len(chunks) - 1


# --- retrieval -------------------------------------------------------------------------------


def test_reciprocal_rank_fusion_rewards_agreement() -> None:
    scores = reciprocal_rank_fusion(
        [[("a", 1), ("b", 2), ("c", 3)], [("c", 1), ("a", 2), ("d", 3)]]
    )

    ranked = sorted(scores, key=scores.__getitem__, reverse=True)
    assert ranked[:2] == ["a", "c"]  # in both lists
    assert scores["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert ranked[-1] == "d"


def test_equal_scores_share_a_rank() -> None:
    assert ranks_from_scores([("a", 2.0), ("b", 2.0), ("c", 1.0), ("d", 1.0), ("e", 0.5)]) == [
        ("a", 1),
        ("b", 1),
        ("c", 3),
        ("d", 3),
        ("e", 5),
    ]


def test_hybrid_retrieval_finds_exact_names(documents, tmp_path: Path) -> None:
    retriever = make_retriever(documents, tmp_path, top_k=3)

    result = retriever.retrieve("What problem does Gamma solve?")

    assert result.chunks[0].chunk.doc_id == "gamma"
    assert retriever.vector_enabled and not result.notes


def test_bm25_only_when_vector_search_is_unavailable(documents) -> None:
    retriever = Retriever(chunk_documents(documents), index=None, embedder=None, glossary={})

    result = retriever.retrieve("Gamma problem")

    assert result.chunks[0].chunk.doc_id == "gamma"
    assert result.notes == ["vector search unavailable: BM25 only"]


def test_glossary_expansion_maps_arabic_terms_to_english(documents, tmp_path: Path) -> None:
    glossary = glossary_terms(documents)

    assert glossary["الفا"] == "Alpha"  # normalized Arabic → English
    assert expand_query("حدثني عن مشروع ألفا", glossary) == "حدثني عن مشروع ألفا Alpha project"
    assert expand_query("Tell me about Alpha", glossary) == "Tell me about Alpha"
    retriever = Retriever(chunk_documents(documents), index=None, embedder=None, glossary=glossary)
    assert retriever.retrieve("ما هي مشكلة ألفا؟").chunks[0].chunk.doc_id == "alpha"


def test_follow_up_uses_the_previous_user_message(documents) -> None:
    retriever = Retriever(chunk_documents(documents), index=None, embedder=None, glossary={})
    question = "What problem does it solve?"  # "it" only makes sense with the previous turn

    alone = [hit.chunk.doc_id for hit in retriever.retrieve(question).chunks]
    follow_up = retriever.retrieve(question, previous_message="Tell me about Beta")

    assert follow_up.chunks[0].chunk.doc_id == "beta"
    assert alone[0] != "beta"  # without the previous turn there is nothing pointing at Beta


def test_results_are_trimmed_to_the_token_budget(documents, tmp_path: Path) -> None:
    roomy = make_retriever(documents, tmp_path, top_k=6, max_context_tokens=10_000)
    tight = make_retriever(documents, tmp_path, top_k=6, max_context_tokens=40)

    full = roomy.retrieve("Alpha Beta Gamma projects")
    trimmed = tight.retrieve("Alpha Beta Gamma projects")

    assert len(full.chunks) == 6
    assert sum(estimate_tokens(hit.chunk.text) for hit in trimmed.chunks) <= 40
    assert trimmed.dropped_for_budget == 6 - len(trimmed.chunks) > 0
    kept = [hit.chunk.id for hit in trimmed.chunks]
    assert kept == [hit.chunk.id for hit in full.chunks if hit.chunk.id in kept]  # best-first order


# --- pinned identity -------------------------------------------------------------------------


def test_identity_context_is_small_and_complete(documents) -> None:
    profile = KnowledgeService(documents).profile
    contact = ContactResponse(
        links=[
            ContactLinkResponse(
                link_id="email", label="Email", url="mailto:t@example.com", kind="email"
            )
        ]
    )

    projects = KnowledgeService(documents).list_projects()
    identity = build_identity_context(profile, contact, projects)

    assert "Name: Test Person (Arabic spelling: شخص)" in identity
    assert "All projects (3): Gamma; Beta; Alpha" in identity  # approved only, featured first
    assert "Headline: Test Engineer" in identity
    assert "Email: t@example.com" in identity
    assert estimate_tokens(identity) <= MAX_IDENTITY_TOKENS
    assert build_identity_context(None, contact) == ""
