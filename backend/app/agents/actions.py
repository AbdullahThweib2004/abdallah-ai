"""Validated UI actions requested by the model.

Protocol (prompt v5): the model starts every reply with ONE line

    ACTIONS: [{"type": "show_project", "project_id": "nawa-inference"}]

(a JSON array, possibly empty), then a newline, then the spoken answer. `ActionPrefixParser`
strips that line from the token stream, and `validate_actions` keeps only allowlisted actions
with known ids. The line never reaches the visitor as text, and nothing in it is trusted:
actions can only open internal cards, never URLs, navigation or HTML.
"""

import json
import logging
import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, ValidationError

logger = logging.getLogger("app.actions")

MAX_ACTIONS = 2
# The ACTIONS line is short; a longer line without a newline is not a valid prefix.
MAX_PREFIX_CHARS = 400
# Wall-clock cap for buffering the prefix (seconds after the first buffered text).
PREFIX_DEADLINE_SECONDS = 1.5
PREFIX = "ACTIONS:"

ProjectId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)]


class _Action(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ShowProject(_Action):
    type: Literal["show_project"]
    project_id: ProjectId


class ShowProjects(_Action):
    type: Literal["show_projects"]


class ShowSkills(_Action):
    type: Literal["show_skills"]


class ShowExperience(_Action):
    type: Literal["show_experience"]


class ShowEducation(_Action):
    type: Literal["show_education"]


class ShowContact(_Action):
    type: Literal["show_contact"]


UiAction = Annotated[
    ShowProject | ShowProjects | ShowSkills | ShowExperience | ShowEducation | ShowContact,
    Field(discriminator="type"),
]
_ADAPTER: TypeAdapter[UiAction] = TypeAdapter(UiAction)
ACTION_TYPES = ("show_project", "show_projects", "show_skills", "show_experience",
                "show_education", "show_contact")  # fmt: skip


def _type_label(item: object) -> str:
    """The `type` of a rejected item, safe to log (only allowlisted names; never free text)."""
    if isinstance(item, dict) and item.get("type") in ACTION_TYPES:
        return str(item["type"])
    return "unknown"


def validate_actions(raw: object, project_ids: Collection[str]) -> list[UiAction]:
    """Keep allowlisted actions with known project ids, without duplicates, at most 2.

    Rejections are logged by action type and reason only (never ids or visitor text).
    """
    if not isinstance(raw, list):
        if raw is not None:
            logger.info("actions rejected reason=not_a_list")
        return []
    actions: list[UiAction] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        try:
            action = _ADAPTER.validate_python(item)
        except ValidationError:
            logger.info("action rejected type=%s reason=invalid", _type_label(item))
            continue
        if isinstance(action, ShowProject) and action.project_id not in project_ids:
            logger.info("action rejected type=show_project reason=unknown_project")
            continue
        key = (action.type, getattr(action, "project_id", ""))
        if key in seen:
            logger.info("action rejected type=%s reason=duplicate", action.type)
            continue
        if len(actions) >= MAX_ACTIONS:
            logger.info("action rejected type=%s reason=over_limit", action.type)
            continue
        seen.add(key)
        actions.append(action)
    return actions


def dump_actions(actions: Iterable[UiAction]) -> list[dict[str, str]]:
    return [action.model_dump() for action in actions]


# --- prefix parsing -----------------------------------------------------------------------------

_DECODER = json.JSONDecoder()
_LEADING = re.compile(r"^\s+")


def _parse_line(line: str) -> tuple[object, str]:
    """Parse `ACTIONS: [...] <rest>` -> (decoded JSON or None, text after the JSON)."""
    body = line.lstrip()[len(PREFIX) :].lstrip()
    try:
        value, end = _DECODER.raw_decode(body)
    except ValueError:
        logger.info("actions rejected reason=malformed_json")
        return None, ""
    return value, body[end:]


def _is_prefix_start(text: str) -> bool:
    """True while `text` could still be (the start of) an ACTIONS line."""
    head = text.lstrip()[: len(PREFIX)].upper()
    return PREFIX.startswith(head) if len(head) < len(PREFIX) else head == PREFIX


@dataclass
class PrefixResult:
    """What the parser decided: `raw` actions (unvalidated) and text to stream on."""

    raw: object
    text: str


@dataclass
class ActionPrefixParser:
    """Separates the ACTIONS line from a streamed answer.

    Feed chunks; once the prefix is decided, `feed` returns a PrefixResult exactly once
    (raw actions + the text that followed), then plain text for every later chunk. If the
    reply does not start with `ACTIONS:`, the decision is `[]` and all text is passed through.
    """

    buffer: str = ""
    decided: bool = False
    # After a deadline cut, the rest of an unfinished ACTIONS line is discarded up to "\n".
    skipping_line: bool = False
    _text_started: bool = field(default=False, repr=False)

    def feed(self, chunk: str) -> PrefixResult | str:
        if self.decided:
            return self._text(chunk)
        self.buffer += chunk
        if not _is_prefix_start(self.buffer):
            return self._decide(None, self.buffer)  # no prefix: everything is answer text
        # The prefix line ends at the first newline after any leading blank lines.
        content_start = len(self.buffer) - len(self.buffer.lstrip())
        newline = self.buffer.find("\n", content_start)
        if newline != -1 and content_start < len(self.buffer):
            raw, rest = _parse_line(self.buffer[:newline])
            # Text after the JSON on the same line ("ACTIONS: [] He…") keeps its line break.
            after = self.buffer[newline:] if rest.strip() else self.buffer[newline + 1 :]
            return self._decide(raw, rest + after)
        if len(self.buffer) > MAX_PREFIX_CHARS:
            return self.finish()
        return ""  # still buffering

    def finish(self) -> PrefixResult | str:
        """End of stream (or the prefix is too long): decide with what is buffered."""
        if self.decided:
            return ""
        if self.buffer.lstrip().upper().startswith(PREFIX):
            raw, rest = _parse_line(self.buffer)
            # Unparseable ACTIONS text is dropped, never shown.
            return self._decide(raw, rest if raw is not None else "")
        if _is_prefix_start(self.buffer):  # only a partial "ACTI…" or whitespace
            return self._decide(None, "")
        return self._decide(None, self.buffer)

    def deadline(self) -> PrefixResult | None:
        """The buffering time cap expired: decide `[]` now and drop the rest of the line."""
        if self.decided:
            return None
        self.skipping_line = self.buffer.strip() != ""
        logger.info("actions rejected reason=prefix_timeout")
        return self._decide(None, "")

    @property
    def buffering(self) -> bool:
        return not self.decided and self.buffer != ""

    def _decide(self, raw: object, text: str) -> PrefixResult:
        self.decided = True
        self.buffer = ""
        return PrefixResult(raw=raw, text=self._text(text))

    def _text(self, chunk: str) -> str:
        if self.skipping_line:
            newline = chunk.find("\n")
            if newline == -1:
                return ""
            self.skipping_line = False
            chunk = chunk[newline + 1 :]
        if not self._text_started:
            # The answer starts after the ACTIONS line: drop the blank lines in between.
            chunk = _LEADING.sub("", chunk)
            self._text_started = bool(chunk)
        return chunk


def split_actions(reply: str, project_ids: Collection[str]) -> tuple[list[UiAction], str]:
    """Parse a complete reply (evals, tests): validated actions and the answer text."""
    parser = ActionPrefixParser()
    first = parser.feed(reply)
    result = first if isinstance(first, PrefixResult) else parser.finish()
    assert isinstance(result, PrefixResult)
    return validate_actions(result.raw, project_ids), result.text
