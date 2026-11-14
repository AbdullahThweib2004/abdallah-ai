from pathlib import Path

import pytest

from app.knowledge.cli import main as cli_main
from app.knowledge.loader import (
    KnowledgeBaseError,
    load_knowledge_base,
    split_sections,
    validate_knowledge_base,
)
from app.knowledge.schemas import ContactMeta

REAL_KNOWLEDGE_BASE = Path(__file__).resolve().parents[2] / "knowledge_base"


def frontmatter(**overrides: object) -> str:
    fields: dict[str, object] = {
        "id": "about",
        "type": "profile",
        "title": '"About"',
        "language": "en",
        "status": "draft",
        "visibility": "public",
        "last_reviewed": "null",
        "tags": "[]",
    }
    fields.update(overrides)
    lines = [f"{key}: {value}" for key, value in fields.items() if value is not None]
    return "---\n" + "\n".join(lines) + "\n---\n"


def write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def errors_by_file(root: Path) -> dict[str, list[str]]:
    return {report.path: report.errors for report in validate_knowledge_base(root)}


APPROVED = {"status": "approved", "last_reviewed": "2026-11-14"}


def test_draft_with_todos_loads_only_when_drafts_included(tmp_path: Path) -> None:
    write(tmp_path, "profile/about.md", frontmatter() + "\n## Summary\n\nTODO: Introduce.\n")

    drafts = load_knowledge_base(tmp_path, include_drafts=True)
    public = load_knowledge_base(tmp_path, include_drafts=False)

    assert [doc.meta.id for doc in drafts] == ["about"]
    assert drafts[0].todo_count == 1
    assert public == []


def test_approved_document_is_loaded_by_default(tmp_path: Path) -> None:
    write(tmp_path, "profile/about.md", frontmatter(**APPROVED) + "\n## Summary\n\nVerified.\n")

    assert [doc.meta.id for doc in load_knowledge_base(tmp_path)] == ["about"]


def test_approved_document_with_todo_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, "profile/about.md", frontmatter(**APPROVED) + "\n## Summary\n\nTODO: x\n")

    errors = errors_by_file(tmp_path)["profile/about.md"]

    assert any("TODO" in error for error in errors)
    with pytest.raises(KnowledgeBaseError):
        load_knowledge_base(tmp_path)


def test_todo_in_frontmatter_comment_blocks_approval(tmp_path: Path) -> None:
    write(tmp_path, "profile/about.md", frontmatter(tags="[]  # TODO add tags", **APPROVED))

    assert any("TODO" in error for error in errors_by_file(tmp_path)["profile/about.md"])


def test_approved_document_without_last_reviewed_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, "profile/about.md", frontmatter(status="approved") + "\n## A\n\nDone.\n")

    errors = errors_by_file(tmp_path)["profile/about.md"]

    assert any("last_reviewed" in error for error in errors)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    write(tmp_path, "profile/about.md", frontmatter(id="same"))
    write(tmp_path, "profile/education.md", frontmatter(id="same"))

    errors = errors_by_file(tmp_path)

    assert any("duplicate id 'same'" in e for e in errors["profile/about.md"])
    assert any("duplicate id 'same'" in e for e in errors["profile/education.md"])


@pytest.mark.parametrize("project_id", ["Banking", "banking_intelligence", "-banking", "a--b"])
def test_non_kebab_case_project_id_is_rejected(tmp_path: Path, project_id: str) -> None:
    write(tmp_path, "projects/p.md", frontmatter(id=project_id, type="project"))

    assert any("kebab-case" in e for e in errors_by_file(tmp_path)["projects/p.md"])


def contact_file(links: str, **overrides: object) -> str:
    return frontmatter(id="public-links", type="contact", **overrides).replace(
        "\n---\n", f"\nlinks:\n{links}---\n", 1
    )


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("http://github.com/someone", "github"),
        ("javascript:alert(1)", "other"),
        ("mailto:someone@example.com", "github"),
        ("https://example.com", "email"),
    ],
)
def test_invalid_link_url_is_rejected(tmp_path: Path, url: str, kind: str) -> None:
    links = f"  - link_id: x\n    label: X\n    url: {url}\n    kind: {kind}\n"
    write(tmp_path, "contact/public_links.md", contact_file(links))

    assert errors_by_file(tmp_path)["contact/public_links.md"]


def test_valid_links_are_accepted(tmp_path: Path) -> None:
    links = (
        "  - link_id: github\n    label: GitHub\n    url: https://github.com/x\n    kind: github\n"
        "  - link_id: email\n    label: Email\n    url: mailto:x@example.com\n    kind: email\n"
    )
    write(tmp_path, "contact/public_links.md", contact_file(links, **APPROVED))

    [doc] = load_knowledge_base(tmp_path)

    assert isinstance(doc.meta, ContactMeta)
    assert [link.link_id for link in doc.meta.links] == ["github", "email"]


def test_duplicate_link_ids_are_rejected(tmp_path: Path) -> None:
    link = "  - link_id: github\n    label: GitHub\n    url: null\n    kind: github\n"
    write(tmp_path, "contact/public_links.md", contact_file(link + link))

    assert any(
        "duplicate link_id" in e for e in errors_by_file(tmp_path)["contact/public_links.md"]
    )


def test_duplicate_link_ids_across_files_are_rejected(tmp_path: Path) -> None:
    link = "  - link_id: github\n    label: GitHub\n    url: null\n    kind: github\n"
    write(tmp_path, "contact/a.md", contact_file(link).replace("public-links", "a"))
    write(tmp_path, "contact/b.md", contact_file(link).replace("public-links", "b"))

    errors = errors_by_file(tmp_path)

    assert any("duplicate link_id 'github'" in e for e in errors["contact/a.md"])


def test_approved_contact_requires_every_url(tmp_path: Path) -> None:
    link = "  - link_id: github\n    label: GitHub\n    url: null\n    kind: github\n"
    write(tmp_path, "contact/public_links.md", contact_file(link, **APPROVED))

    assert any("requires a url" in e for e in errors_by_file(tmp_path)["contact/public_links.md"])


def test_unknown_frontmatter_field_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, "profile/about.md", frontmatter(secret_note="hello"))

    errors = errors_by_file(tmp_path)["profile/about.md"]

    assert any("secret_note" in e for e in errors)


def test_private_visibility_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, "profile/about.md", frontmatter(visibility="private"))

    assert any("visibility" in e for e in errors_by_file(tmp_path)["profile/about.md"])


def test_type_must_match_folder(tmp_path: Path) -> None:
    write(tmp_path, "projects/about.md", frontmatter())

    assert any("not allowed" in e for e in errors_by_file(tmp_path)["projects/about.md"])


def test_missing_frontmatter_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, "profile/about.md", "## Summary\n\nNo frontmatter.\n")

    assert errors_by_file(tmp_path)["profile/about.md"] == ["missing YAML frontmatter"]


def test_template_private_and_readme_files_are_ignored(tmp_path: Path) -> None:
    write(tmp_path, "profile/about.md", frontmatter())
    write(tmp_path, "projects/_TEMPLATE.md", "not valid frontmatter at all")
    write(tmp_path, "_private/never_public.md", "secret, no frontmatter")
    write(tmp_path, "_private/nested/notes.md", "secret")
    write(tmp_path, "README.md", "# Readme")
    write(tmp_path, "projects/README.md", "# Readme")

    reports = validate_knowledge_base(tmp_path)

    assert [report.path for report in reports] == ["profile/about.md"]
    assert not reports[0].errors


def test_sections_are_split_by_level_two_heading() -> None:
    body = (
        "# Project: Demo\n\n"
        "<!-- authoring note -->\n"
        "## Problem\n\nFirst paragraph.\n\nSecond paragraph.\n\n"
        "### Detail\n\nStays inside Problem.\n\n"
        "## Architecture\n\n```text\n## not a heading\n```\n"
    )

    sections = split_sections(body)

    assert [section.heading for section in sections] == ["Problem", "Architecture"]
    assert sections[0].content == (
        "First paragraph.\n\nSecond paragraph.\n\n### Detail\n\nStays inside Problem."
    )
    assert "## not a heading" in sections[1].content
    assert sections[0].text.startswith("## Problem\n\nFirst paragraph.")
    assert "authoring note" not in "".join(section.text for section in sections)


def test_text_before_first_heading_is_kept_without_title() -> None:
    sections = split_sections("# Title\n\nIntro text.\n\n## A\n\nBody.\n")

    assert [(s.heading, s.content) for s in sections] == [(None, "Intro text."), ("A", "Body.")]


def test_missing_root_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        validate_knowledge_base(tmp_path / "missing")


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, "profile/about.md", frontmatter())
    assert cli_main(["validate", "--root", str(tmp_path)]) == 0

    write(tmp_path, "profile/bad.md", frontmatter(id="about"))
    assert cli_main(["validate", "--root", str(tmp_path)]) == 1
    assert "duplicate id 'about'" in capsys.readouterr().out


def test_real_knowledge_base_is_valid() -> None:
    reports = validate_knowledge_base(REAL_KNOWLEDGE_BASE)

    assert reports, "expected knowledge files in knowledge_base/"
    assert {report.path: report.errors for report in reports if report.errors} == {}
    assert load_knowledge_base(REAL_KNOWLEDGE_BASE, include_drafts=True)
