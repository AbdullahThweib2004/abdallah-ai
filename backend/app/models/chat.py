from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_MESSAGE_CHARS = 800
MAX_HISTORY_TURNS = 8
MAX_TURN_CHARS = 2000


class ChatTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TURN_CHARS)
    ]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)
    ]
    history: list[ChatTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)
    ui_language: Literal["en", "ar"] = "en"


class RateLimitResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str
    code: Literal["rate_limited", "daily_limit", "daily_cap"]
