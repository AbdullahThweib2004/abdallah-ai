"""Deterministic provider for tests and for running the app without any API key."""

import asyncio
import re
from collections.abc import AsyncIterator

from app.llm.base import ChatMessage, LLMChunk, LLMError, Usage

DEMO_EN = (
    "This is a demo answer: Abdallah AI is running without a language model, so it cannot "
    "answer real questions yet. Meanwhile, the cards and the About page show his verified "
    "projects and experience."
)
DEMO_AR = (
    "هذه إجابة تجريبية: يعمل Abdallah AI حالياً دون نموذج لغوي، لذلك لا يستطيع الإجابة عن "
    "الأسئلة الحقيقية بعد. في الأثناء، تعرض البطاقات وصفحة النبذة مشاريعه وخبراته الموثّقة."
)
_ARABIC = re.compile(r"[\u0600-\u06FF]")


class FakeProvider:
    name = "fake"

    def __init__(
        self,
        *,
        answer: str | None = None,
        delay: float = 0.0,
        error: LLMError | None = None,
        error_after_tokens: int | None = None,
        hang_seconds: float = 0.0,
    ) -> None:
        self.model = "fake-demo"
        self._answer = answer
        self._delay = delay
        self._error = error
        self._error_after_tokens = error_after_tokens
        self._hang_seconds = hang_seconds
        self.calls: list[list[ChatMessage]] = []

    async def stream(
        self, messages: list[ChatMessage], *, max_tokens: int, temperature: float
    ) -> AsyncIterator[LLMChunk]:
        self.calls.append(messages)
        if self._hang_seconds:
            await asyncio.sleep(self._hang_seconds)
        if self._error and self._error_after_tokens is None:
            raise self._error

        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        answer = self._answer or (DEMO_AR if _ARABIC.search(last_user) else DEMO_EN)
        words = answer.split(" ")
        for index, word in enumerate(words):
            if self._error and index == self._error_after_tokens:
                raise self._error
            if self._delay:
                await asyncio.sleep(self._delay)
            yield LLMChunk(text=word if index == 0 else f" {word}")
        prompt_tokens = sum(len(m["content"]) for m in messages) // 4
        yield LLMChunk(usage=Usage(prompt_tokens, len(words)), model=self.model)

    async def aclose(self) -> None:
        return None
