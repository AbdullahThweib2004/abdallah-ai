"""Read-only access to the approved knowledge base for the public content API.

The knowledge base is loaded once at startup (see `app.main`). Only approved documents are
loaded, and every response is derived from them by document id and section heading;
no facts about Abdallah live in code.
"""

import logging
import re
from collections.abc import Iterable
from pathlib import Path

from app.knowledge.loader import KnowledgeBaseError, KnowledgeDocument, load_knowledge_base
from app.knowledge.schemas import ContactMeta, ProjectMeta
from app.models.content import (
    ContactLinkResponse,
    ContactResponse,
    ContentSection,
    Experience,
    Interests,
    Intro,
    ProfileResponse,
    ProjectDetail,
    ProjectSummary,
    SkillGroup,
)

logger = logging.getLogger(__name__)

# Document ids the profile is assembled from (stable ids from knowledge_base/).
ABOUT_ID = "about"
EDUCATION_ID = "education"
EXPERIENCE_ID = "experience"
SKILLS_ID = "skills"
INTERESTS_ID = "interests"
GOALS_ID = "goals"
GLOSSARY_ID = "terms-ar-en"

# Project sections whose body starts with this marker only point at frontmatter fields.
SEE_FRONTMATTER = "See frontmatter."

_BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
_INTRO_LINE = re.compile(r'^(English|Arabic):\s*"(.+)"\s*$', re.MULTILINE)
_TABLE_ROW = re.compile(r"^\|(.+)\|\s*$")


class ProfileUnavailableError(Exception):
    """The approved knowledge base lacks content the profile requires."""


def visible_sections(document: KnowledgeDocument) -> list[ContentSection]:
    """Headed sections, minus bodies that only say "See frontmatter.".

    Text after the marker (e.g. an extra sentence under "Status") is kept.
    """
    sections = []
    for section in document.sections:
        if section.heading is None:
            continue
        body = section.content
        if body.startswith(SEE_FRONTMATTER):
            body = body.removeprefix(SEE_FRONTMATTER).strip()
        if body:
            sections.append(ContentSection(heading=section.heading, body_markdown=body))
    return sections


def split_list(text: str) -> list[str]:
    """Split "a, b (c, d), and e." into ["a", "b (c, d)", "e"], ignoring commas in brackets."""
    items: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text.strip().removesuffix("."):
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(depth - 1, 0)
        if char == "," and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(char)
    items.append("".join(current))
    cleaned = (item.strip().removeprefix("and ").strip() for item in items)
    return [item for item in cleaned if item]


def split_bullets(text: str) -> tuple[str | None, list[str]]:
    """Separate a Markdown body into its non-bullet prose and its bullet items."""
    prose: list[str] = []
    bullets: list[str] = []
    for line in text.splitlines():
        match = _BULLET.match(line)
        if match:
            bullets.append(match.group(1).strip())
        elif line.strip():
            prose.append(line.strip())
    return (" ".join(prose) or None), bullets


class KnowledgeService:
    def __init__(self, documents: Iterable[KnowledgeDocument]) -> None:
        approved = [doc for doc in documents if doc.meta.status == "approved"]
        self._documents = {doc.meta.id: doc for doc in approved}

        projects = [doc for doc in approved if isinstance(doc.meta, ProjectMeta)]
        projects.sort(key=lambda doc: (not doc.meta.featured, doc.meta.order, doc.meta.title))
        self._projects = {doc.meta.id: doc for doc in projects}

        self.profile_error: str | None = None
        self.profile: ProfileResponse | None = None
        try:
            self.profile = self._build_profile()
        except ProfileUnavailableError as exc:
            self.profile_error = str(exc)
            logger.error("Profile content unavailable: %s", exc)

    @property
    def approved_documents(self) -> int:
        return len(self._documents)

    # --- projects -------------------------------------------------------------------------

    def list_projects(self) -> list[ProjectSummary]:
        return [self._project_summary(doc) for doc in self._projects.values()]

    def get_project(self, project_id: str) -> ProjectDetail | None:
        doc = self._projects.get(project_id)
        if doc is None:
            return None
        summary = self._project_summary(doc)
        return ProjectDetail(
            **summary.model_dump(),
            last_reviewed=doc.meta.last_reviewed,
            sections=visible_sections(doc),
        )

    @staticmethod
    def _project_summary(doc: KnowledgeDocument) -> ProjectSummary:
        meta = doc.meta
        assert isinstance(meta, ProjectMeta)
        return ProjectSummary(
            id=meta.id,
            title=meta.title,
            one_line_summary=_section_body(doc, "One-line summary"),
            project_status=meta.project_status,
            technologies=list(meta.technologies),
            featured=meta.featured,
            repository_url=meta.repository_url,
            demo_url=meta.demo_url,
            tags=list(meta.tags),
        )

    # --- contact --------------------------------------------------------------------------

    def contact(self) -> ContactResponse:
        links = [
            ContactLinkResponse(
                link_id=link.link_id, label=link.label, url=link.url, kind=link.kind
            )
            for doc in self._documents.values()
            if isinstance(doc.meta, ContactMeta)
            for link in doc.meta.links
            if link.url is not None
        ]
        return ContactResponse(links=links)

    # --- profile --------------------------------------------------------------------------

    def _build_profile(self) -> ProfileResponse:
        about = self._documents.get(ABOUT_ID)
        if about is None:
            raise ProfileUnavailableError(f"approved document '{ABOUT_ID}' is missing")
        headline = _section_body(about, "Headline")
        summary = _section_body(about, "Summary")
        if headline is None or summary is None:
            raise ProfileUnavailableError(f"'{ABOUT_ID}' needs 'Headline' and 'Summary' sections")

        # The about document is titled "About <name>".
        name = re.sub(r"^About\s+", "", about.meta.title).strip()
        location = _section_body(about, "Location")
        languages = _section_body(about, "Languages")

        return ProfileResponse(
            name=name,
            name_ar=self._arabic_term(name),
            headline=headline,
            summary_markdown=summary,
            location=location.removesuffix(".") if location else None,
            languages=split_list(languages) if languages else [],
            intro=_parse_intro(_section_body(about, "Short self-introduction")),
            ways_of_working=_section_body(about, "Ways of working"),
            education=self._sections_of(EDUCATION_ID),
            experience=self._experience(),
            skills=self._skills(),
            interests=self._interests(),
            career_direction=self._sections_of(GOALS_ID),
        )

    def _sections_of(self, document_id: str) -> list[ContentSection]:
        doc = self._documents.get(document_id)
        return visible_sections(doc) if doc else []

    def _experience(self) -> Experience | None:
        doc = self._documents.get(EXPERIENCE_ID)
        if doc is None:
            return None
        return Experience(title=doc.meta.title, sections=visible_sections(doc))

    def _skills(self) -> list[SkillGroup]:
        groups = []
        for section in self._sections_of(SKILLS_ID):
            prose, bullets = split_bullets(section.body_markdown)
            items = bullets or (split_list(prose) if prose else [])
            groups.append(SkillGroup(category=section.heading, items=items))
        return groups

    def _interests(self) -> Interests:
        prose_parts: list[str] = []
        items: list[str] = []
        for section in self._sections_of(INTERESTS_ID):
            prose, bullets = split_bullets(section.body_markdown)
            if prose:
                prose_parts.append(prose)
            items.extend(bullet.removesuffix(".") for bullet in bullets)
        return Interests(summary=" ".join(prose_parts) or None, items=items)

    def _arabic_term(self, english: str) -> str | None:
        """Look up the Arabic form of a term in the glossary tables."""
        doc = self._documents.get(GLOSSARY_ID)
        if doc is None:
            return None
        for section in doc.sections:
            for line in section.content.splitlines():
                match = _TABLE_ROW.match(line.strip())
                if not match:
                    continue
                cells = [cell.strip() for cell in match.group(1).split("|")]
                if len(cells) >= 2 and cells[0] == english and cells[1]:
                    return cells[1]
        return None


def _section_body(doc: KnowledgeDocument, heading: str) -> str | None:
    for section in doc.sections:
        if section.heading and section.heading.casefold() == heading.casefold():
            return section.content.strip() or None
    return None


def _parse_intro(body: str | None) -> Intro:
    found = dict(_INTRO_LINE.findall(body or ""))
    return Intro(en=found.get("English"), ar=found.get("Arabic"))


def load_knowledge_service(root: Path) -> KnowledgeService | None:
    """Load approved documents, or return None (and log why) if the knowledge base is invalid."""
    try:
        documents = load_knowledge_base(root, include_drafts=False)
    except (KnowledgeBaseError, OSError, ValueError) as exc:
        logger.error("Knowledge base failed to load from %s: %s", root, exc)
        return None
    logger.info("Loaded %d approved knowledge documents from %s", len(documents), root)
    return KnowledgeService(documents)
