from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.knowledge_service import split_list
from tests.conftest import REAL_KNOWLEDGE_BASE

CONTENT_ROUTES = [
    "/api/v1/profile",
    "/api/v1/projects",
    "/api/v1/projects/alpha",
    "/api/v1/contact",
]


# --- projects ------------------------------------------------------------------------------


def test_projects_are_approved_only_and_sorted(client: TestClient) -> None:
    response = client.get("/api/v1/projects")

    assert response.status_code == 200
    # featured first (gamma order 1, beta order 2), then non-featured; the draft is excluded.
    assert [project["id"] for project in response.json()] == ["gamma", "beta", "alpha"]


def test_project_summary_shape(client: TestClient) -> None:
    project = client.get("/api/v1/projects").json()[0]

    assert project == {
        "id": "gamma",
        "title": "Gamma",
        "one_line_summary": "Summary of Gamma.",
        "project_status": "completed",
        "technologies": ["Python", "FastAPI"],
        "featured": True,
        "repository_url": "https://github.com/example/gamma",
        "demo_url": None,
        "tags": [],
    }


def test_project_detail_filters_frontmatter_pointer_sections(client: TestClient) -> None:
    response = client.get("/api/v1/projects/alpha")

    assert response.status_code == 200
    body = response.json()
    assert body["last_reviewed"] == "2026-01-01"
    assert body["sections"] == [
        {"heading": "Status", "body_markdown": "Two of three phases are done."},
        {"heading": "One-line summary", "body_markdown": "Summary of Alpha."},
        {"heading": "Problem", "body_markdown": "A **real** problem."},
    ]


def test_draft_project_is_never_returned(client: TestClient) -> None:
    assert client.get("/api/v1/projects/secret-draft").status_code == 404


def test_unknown_project_returns_json_404(client: TestClient) -> None:
    response = client.get("/api/v1/projects/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found."}


def test_invalid_project_id_is_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/projects/Not_Valid").status_code == 422


# --- profile -------------------------------------------------------------------------------


def test_profile_is_derived_from_sections(client: TestClient) -> None:
    response = client.get("/api/v1/profile")

    assert response.status_code == 200
    profile = response.json()
    assert profile["name"] == "Test Person"
    assert profile["name_ar"] == "شخص"
    assert profile["headline"] == "Test Engineer"
    assert profile["location"] == "Testland"
    assert profile["languages"] == ["English (fluent)", "German (basic, A1)"]
    assert profile["intro"] == {"en": "Hi, I am the AI version of Test Person.", "ar": "مرحبا"}
    assert profile["education"] == [{"heading": "Degree", "body_markdown": "B.Sc. Test."}]
    assert profile["experience"]["title"] == "Test Training"
    assert [s["heading"] for s in profile["experience"]["sections"]] == ["Role", "Duties"]
    assert profile["skills"] == [
        {"category": "Languages", "items": ["Python", "C++ (C++20, C++17)", "TypeScript"]},
        {"category": "AI", "items": ["RAG: retrieval, with citations.", "MCP servers."]},
    ]
    assert profile["interests"] == {"summary": "Intro text.", "items": ["AI", "Security"]}
    assert profile["career_direction"] == [{"heading": "Focus", "body_markdown": "Build things."}]


def test_profile_without_about_document_returns_503(
    make_client: Callable[[Path], TestClient], fixture_kb: Path
) -> None:
    (fixture_kb / "profile" / "about.md").unlink()
    client = make_client(fixture_kb)

    assert client.get("/api/v1/profile").status_code == 503
    assert client.get("/api/v1/projects").status_code == 200


def test_split_list_respects_brackets() -> None:
    assert split_list("A, B (x, y), and C.") == ["A", "B (x, y)", "C"]


# --- contact -------------------------------------------------------------------------------


def test_contact_returns_public_links(client: TestClient) -> None:
    response = client.get("/api/v1/contact")

    assert response.status_code == 200
    assert response.json() == {
        "links": [
            {
                "link_id": "github",
                "label": "GitHub",
                "url": "https://github.com/example",
                "kind": "github",
            },
            {
                "link_id": "email",
                "label": "Email",
                "url": "mailto:test@example.com",
                "kind": "email",
            },
        ]
    }


# --- failure mode --------------------------------------------------------------------------


@pytest.mark.parametrize("route", CONTENT_ROUTES)
def test_content_routes_return_503_when_knowledge_base_fails(
    make_client: Callable[[Path], TestClient], fixture_kb: Path, route: str
) -> None:
    # An approved document with a TODO makes the whole knowledge base invalid.
    about = fixture_kb / "profile" / "about.md"
    about.write_text(about.read_text(encoding="utf-8") + "\nTODO: unfinished\n", encoding="utf-8")
    client = make_client(fixture_kb)

    response = client.get(route)

    assert response.status_code == 503
    assert response.json() == {"detail": "Portfolio content is temporarily unavailable."}
    assert str(fixture_kb) not in response.text


def test_responses_do_not_expose_file_paths(client: TestClient) -> None:
    for route in CONTENT_ROUTES:
        text = client.get(route).text
        assert ".md" not in text
        assert "path" not in client.get(route).json()


# --- real knowledge base -------------------------------------------------------------------


def test_smoke_real_knowledge_base(make_client: Callable[[Path], TestClient]) -> None:
    client = make_client(REAL_KNOWLEDGE_BASE)

    health = client.get("/api/v1/health").json()
    projects = client.get("/api/v1/projects").json()

    assert health["knowledge_base"] == "ok"
    assert health["approved_documents"] > 0
    assert client.get("/api/v1/profile").status_code == 200
    assert client.get("/api/v1/contact").status_code == 200
    assert projects
    featured = [project["featured"] for project in projects]
    assert featured == sorted(featured, reverse=True)
    for project in projects:
        assert client.get(f"/api/v1/projects/{project['id']}").status_code == 200
