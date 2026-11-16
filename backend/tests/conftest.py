from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.llm.base import LLMProvider
from app.main import create_app
from app.services.rate_limit import RateLimiter

REAL_KNOWLEDGE_BASE = Path(__file__).resolve().parents[2] / "knowledge_base"

APPROVED = "status: approved\nlast_reviewed: 2026-01-01"
DRAFT = "status: draft\nlast_reviewed: null"


def _doc(
    doc_id: str, doc_type: str, title: str, body: str, extra: str = "", status: str = APPROVED
) -> str:
    return (
        f'---\nid: {doc_id}\ntype: {doc_type}\ntitle: "{title}"\nlanguage: en\n{status}\n'
        f"visibility: public\ntags: []\n{extra}---\n# {title}\n\n{body}"
    )


def _project(
    project_id: str, title: str, *, featured: bool, order: int, status: str = APPROVED
) -> str:
    extra = (
        f"project_status: completed\ntechnologies: [Python, FastAPI]\n"
        f"repository_url: https://github.com/example/{project_id}\ndemo_url: null\n"
        f"featured: {str(featured).lower()}\norder: {order}\n"
    )
    body = (
        "## Project ID\nSee frontmatter.\n\n"
        "## Status\nSee frontmatter. Two of three phases are done.\n\n"
        f"## One-line summary\nSummary of {title}.\n\n"
        "## Problem\nA **real** problem.\n\n"
        "## Technologies\nSee frontmatter.\n\n"
        "## Public repository\nSee frontmatter.\n\n"
        "## Last reviewed\nSee frontmatter.\n"
    )
    return _doc(project_id, "project", title, body, extra, status)


def write_fixture_kb(root: Path) -> Path:
    """A small, fully synthetic knowledge base (no real facts) for API tests."""
    files = {
        "profile/about.md": _doc(
            "about",
            "profile",
            "About Test Person",
            "## Headline\nTest Engineer\n\n## Summary\nTest summary.\n\n## Location\nTestland.\n\n"
            "## Languages\nEnglish (fluent), German (basic, A1).\n\n"
            "## Short self-introduction\nThe greeting.\n\n"
            'English: "Hi, I am the AI version of Test Person."\n\n'
            'Arabic: "مرحبا"\n',
        ),
        "profile/education.md": _doc(
            "education", "profile", "Education", "## Degree\nB.Sc. Test.\n"
        ),
        "profile/experience.md": _doc(
            "experience",
            "profile",
            "Test Training",
            "## Role\nIntern.\n\n## Duties\n- One\n- Two\n",
        ),
        "profile/skills.md": _doc(
            "skills",
            "profile",
            "Skills",
            "## Languages\nPython, C++ (C++20, C++17), and TypeScript.\n\n"
            "## AI\n- RAG: retrieval, with citations.\n- MCP servers.\n",
        ),
        "career/interests.md": _doc(
            "interests",
            "career",
            "Interests",
            "## Professional interests\nIntro text.\n- AI.\n- Security.\n",
        ),
        "career/goals.md": _doc("goals", "career", "Direction", "## Focus\nBuild things.\n"),
        "contact/public_links.md": _doc(
            "public-links",
            "contact",
            "Links",
            "## Reach\nBy email.\n",
            "links:\n"
            "  - link_id: github\n    label: GitHub\n"
            "    url: https://github.com/example\n    kind: github\n"
            "  - link_id: email\n    label: Email\n"
            "    url: mailto:test@example.com\n    kind: email\n",
        ),
        "glossary/terms.md": _doc(
            "terms-ar-en",
            "glossary",
            "Terms",
            "## Names\n| English | Arabic | Notes |\n|---|---|---|\n| Test Person | شخص | |\n",
        ),
        "projects/alpha.md": _project("alpha", "Alpha", featured=False, order=1),
        "projects/beta.md": _project("beta", "Beta", featured=True, order=2),
        "projects/gamma.md": _project("gamma", "Gamma", featured=True, order=1),
        "projects/draft.md": _project(
            "secret-draft", "Draft", featured=True, order=0, status=DRAFT
        ),
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def fixture_kb(tmp_path: Path) -> Path:
    return write_fixture_kb(tmp_path / "knowledge_base")


def make_settings(knowledge_base_dir: Path, **overrides: Any) -> Settings:
    """Settings that ignore any real `.env`, so tests never use a developer's API key."""
    values: dict[str, Any] = {
        "app_env": "test",
        "cors_origins": ["http://localhost:3000"],
        "knowledge_base_dir": knowledge_base_dir,
        "llm_provider": "fake",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def make_client() -> Iterator[Callable[..., TestClient]]:
    """Build a client for a knowledge base dir; runs the app lifespan.

    Keyword arguments are settings overrides, plus an optional `provider` (an LLMProvider
    instance) and `rate_limiter`.
    """
    clients: list[TestClient] = []

    def factory(
        knowledge_base_dir: Path,
        *,
        provider: LLMProvider | None = None,
        rate_limiter: RateLimiter | None = None,
        **overrides: Any,
    ) -> TestClient:
        settings = make_settings(knowledge_base_dir, **overrides)
        app = create_app(settings, llm_provider=provider, rate_limiter=rate_limiter)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: Callable[..., TestClient], fixture_kb: Path) -> TestClient:
    return make_client(fixture_kb)
