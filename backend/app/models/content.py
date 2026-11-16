"""Public response models for the read-only portfolio content API.

These models expose only what the website needs: no file paths, review metadata
beyond `last_reviewed`, or other internal fields.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.knowledge.schemas import LinkKind, ProjectStatus


class _Response(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContentSection(_Response):
    heading: str
    body_markdown: str


class Intro(_Response):
    en: str | None
    ar: str | None


class Experience(_Response):
    title: str
    sections: list[ContentSection]


class SkillGroup(_Response):
    category: str
    items: list[str]


class Interests(_Response):
    summary: str | None
    items: list[str]


class ProfileResponse(_Response):
    name: str
    name_ar: str | None
    headline: str
    summary_markdown: str
    location: str | None
    languages: list[str]
    intro: Intro
    ways_of_working: str | None
    education: list[ContentSection]
    experience: Experience | None
    skills: list[SkillGroup]
    interests: Interests
    career_direction: list[ContentSection]


class ProjectSummary(_Response):
    id: str
    title: str
    one_line_summary: str | None
    project_status: ProjectStatus | None
    technologies: list[str]
    featured: bool
    repository_url: str | None
    demo_url: str | None
    tags: list[str]


class ProjectDetail(ProjectSummary):
    last_reviewed: date | None
    sections: list[ContentSection]


class ContactLinkResponse(_Response):
    link_id: str
    label: str
    url: str
    kind: LinkKind


class ContactResponse(_Response):
    links: list[ContactLinkResponse]


class ErrorResponse(_Response):
    detail: str


KnowledgeBaseHealth = Literal["ok", "error"]
