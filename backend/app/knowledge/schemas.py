"""Frontmatter schemas for knowledge base documents.

Every Markdown file in `knowledge_base/` starts with YAML frontmatter that must match exactly one
of these models (selected by `type`). Unknown fields are rejected.
"""

import re
from datetime import date
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

KEBAB_CASE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

DocType = Literal["profile", "project", "career", "contact", "glossary"]
Language = Literal["en", "ar"]
Status = Literal["draft", "approved"]
ProjectStatus = Literal["completed", "in_progress", "research"]
LinkKind = Literal["github", "linkedin", "email", "demo", "other"]


def _require_kebab_case(value: str) -> str:
    if not KEBAB_CASE.fullmatch(value):
        raise ValueError(f"'{value}' must be kebab-case (^[a-z0-9]+(-[a-z0-9]+)*$)")
    return value


def _require_https(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"'{url}' must be an absolute https:// URL")
    return url


def _require_mailto(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "mailto" or "@" not in parsed.path:
        raise ValueError(f"'{url}' must be a mailto: address")
    return url


class _BaseMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    id: str
    title: str = Field(min_length=1)
    language: Language
    status: Status
    visibility: Literal["public"]
    last_reviewed: date | None = None
    tags: list[str] = []

    @field_validator("id")
    @classmethod
    def _id_is_kebab_case(cls, value: str) -> str:
        return _require_kebab_case(value)

    @model_validator(mode="after")
    def _approved_requires_review_date(self) -> "_BaseMeta":
        if self.status == "approved" and self.last_reviewed is None:
            raise ValueError("status 'approved' requires last_reviewed (YYYY-MM-DD)")
        return self


class ProfileMeta(_BaseMeta):
    type: Literal["profile"]


class CareerMeta(_BaseMeta):
    type: Literal["career"]


class GlossaryMeta(_BaseMeta):
    type: Literal["glossary"]


class ProjectMeta(_BaseMeta):
    type: Literal["project"]
    project_status: ProjectStatus | None = None
    technologies: list[str] = []
    repository_url: str | None = None
    demo_url: str | None = None
    featured: bool = False
    order: int = 0

    @field_validator("repository_url", "demo_url")
    @classmethod
    def _urls_are_https(cls, value: str | None) -> str | None:
        return None if value is None else _require_https(value)

    @model_validator(mode="after")
    def _approved_requires_project_status(self) -> "ProjectMeta":
        if self.status == "approved" and self.project_status is None:
            raise ValueError("status 'approved' requires project_status")
        return self


class ContactLink(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    link_id: str
    label: str = Field(min_length=1)
    url: str | None = None
    kind: LinkKind

    @field_validator("link_id")
    @classmethod
    def _link_id_is_kebab_case(cls, value: str) -> str:
        return _require_kebab_case(value)

    @model_validator(mode="after")
    def _url_matches_kind(self) -> "ContactLink":
        if self.url is not None:
            if self.kind == "email":
                _require_mailto(self.url)
            else:
                _require_https(self.url)
        return self


class ContactMeta(_BaseMeta):
    type: Literal["contact"]
    links: list[ContactLink] = []

    @model_validator(mode="after")
    def _links_are_valid(self) -> "ContactMeta":
        link_ids = [link.link_id for link in self.links]
        duplicates = sorted({link_id for link_id in link_ids if link_ids.count(link_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate link_id(s): {', '.join(duplicates)}")
        if self.status == "approved":
            missing = [link.link_id for link in self.links if link.url is None]
            if missing:
                raise ValueError(f"status 'approved' requires a url for: {', '.join(missing)}")
        return self


KnowledgeMeta = Annotated[
    ProfileMeta | ProjectMeta | CareerMeta | ContactMeta | GlossaryMeta,
    Field(discriminator="type"),
]

knowledge_meta_adapter: TypeAdapter[KnowledgeMeta] = TypeAdapter(KnowledgeMeta)
