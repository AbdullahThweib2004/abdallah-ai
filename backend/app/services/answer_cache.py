"""Answer cache for FIRST-turn questions (no history), plus the TTS audio of cached answers.

A full reply (answer text, validated actions, sources) is stored under a key made of the
normalized question, the reply language, the knowledge-base hash and the prompt version, so
any knowledge or prompt change starts a fresh cache. Follow-ups (with history) are never cached:
their answers depend on the conversation.

Persistence (optional, `ANSWER_CACHE_DIR`): one JSON file per answer and one MP3 per spoken
sentence, under a namespace folder for the current knowledge hash + prompt version; folders of
older namespaces are deleted at startup. Only hashes of questions are stored, never the
question text. The audio is the assistant's synthesized voice, never visitor audio.
"""

import hashlib
import json
import logging
import re
import shutil
import time
import unicodedata
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Part of every key AND of the folder name: bumping it drops all stored answers on the next
# start (2: only main-model answers that pass the rule checks are stored).
CACHE_FORMAT = 2

_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670\u0640]")  # Arabic harakat, dagger alef, tatweel
_APOSTROPHES = re.compile(r"['\u2019`]")
_ALEF = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي"})
_WHITESPACE = re.compile(r"\s+")
_NAMESPACE = re.compile(r"[0-9a-f]{16}")


def normalize_question(text: str) -> str:
    """Case, punctuation, Arabic diacritics/alef forms and spacing do not change the key:
    "What's his strongest project?" == "whats his strongest project"."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = _DIACRITICS.sub("", text).translate(_ALEF)
    text = _APOSTROPHES.sub("", text)
    text = "".join(
        " " if unicodedata.category(char)[0] in "PS" else char for char in text
    )  # punctuation and symbols (incl. ؟ ، «») become spaces
    return _WHITESPACE.sub(" ", text).strip()


def cache_key(question: str, language: str, kb_hash: str, prompt_version: str) -> str:
    payload = json.dumps(
        [CACHE_FORMAT, normalize_question(question), language, kb_hash, prompt_version],
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _squash(text: str) -> str:
    """Whitespace-free form for matching spoken sentences against answers (the frontend may
    add a space between Arabic and Latin letters before speaking)."""
    return _WHITESPACE.sub("", unicodedata.normalize("NFKC", text))


@dataclass(frozen=True)
class CachedReply:
    text: str
    actions: list[dict[str, Any]]
    sources: list[dict[str, str]]
    language: str
    model: str
    created_at: float = field(default_factory=time.time)


class AnswerCache:
    def __init__(
        self,
        *,
        kb_hash: str,
        prompt_version: str,
        directory: Path | None = None,
        max_entries: int = 500,
    ) -> None:
        self.kb_hash = kb_hash
        self.prompt_version = prompt_version
        self._max = max_entries
        self._replies: OrderedDict[str, CachedReply] = OrderedDict()
        self._squashed: dict[str, tuple[str, str]] = {}  # key -> (language, squashed text)
        self._audio: OrderedDict[str, bytes] = OrderedDict()
        self._dir: Path | None = None
        if directory is not None:
            namespace = hashlib.sha256(
                f"{CACHE_FORMAT}|{kb_hash}|{prompt_version}".encode()
            ).hexdigest()[:16]
            self._dir = directory / namespace
            self._load(directory)

    # --- answers ---------------------------------------------------------------------------

    def key_for(self, question: str, language: str) -> str:
        return cache_key(question, language, self.kb_hash, self.prompt_version)

    def get(self, key: str) -> CachedReply | None:
        reply = self._replies.get(key)
        if reply is not None:
            self._replies.move_to_end(key)
        return reply

    def put(self, key: str, reply: CachedReply) -> None:
        self._remember(key, reply)
        if self._dir is not None:
            try:
                (self._dir / "answers").mkdir(parents=True, exist_ok=True)
                path = self._dir / "answers" / f"{key}.json"
                path.write_text(json.dumps(asdict(reply), ensure_ascii=False), encoding="utf-8")
            except OSError as exc:
                logger.warning("Answer cache: could not persist an answer (%s)", exc)

    def __len__(self) -> int:
        return len(self._replies)

    def _remember(self, key: str, reply: CachedReply) -> None:
        self._replies[key] = reply
        self._replies.move_to_end(key)
        self._squashed[key] = (reply.language, _squash(reply.text))
        while len(self._replies) > self._max:
            old, _ = self._replies.popitem(last=False)
            self._squashed.pop(old, None)
            if self._dir is not None:
                (self._dir / "answers" / f"{old}.json").unlink(missing_ok=True)

    # --- speech ----------------------------------------------------------------------------

    def speech_cacheable(self, text: str, language: str) -> bool:
        """True when `text` (one spoken sentence) is part of a cached answer."""
        squashed = _squash(text)
        if len(squashed) < 2:
            return False
        return any(
            lang == language and squashed in answer for lang, answer in self._squashed.values()
        )

    @staticmethod
    def audio_key(spoken: str, language: str, voice: str) -> str:
        payload = json.dumps([CACHE_FORMAT, _squash(spoken), language, voice], ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get_audio(self, key: str) -> bytes | None:
        audio = self._audio.get(key)
        if audio is None and self._dir is not None:
            path = self._dir / "audio" / f"{key}.mp3"
            if path.is_file():
                audio = path.read_bytes()
                self._audio[key] = audio
        if audio is not None:
            self._audio.move_to_end(key)
        return audio

    def put_audio(self, key: str, audio: bytes) -> None:
        self._audio[key] = audio
        while len(self._audio) > self._max * 4:  # a few sentences per answer
            self._audio.popitem(last=False)
        if self._dir is not None:
            try:
                (self._dir / "audio").mkdir(parents=True, exist_ok=True)
                (self._dir / "audio" / f"{key}.mp3").write_bytes(audio)
            except OSError as exc:
                logger.warning("Answer cache: could not persist audio (%s)", exc)

    # --- persistence -----------------------------------------------------------------------

    def _load(self, root: Path) -> None:
        assert self._dir is not None
        if root.is_dir():
            # Older knowledge/prompt versions can never be hit again.
            # Only folders this cache created (16 hex characters) are ever removed.
            for stale in root.iterdir():
                if stale.is_dir() and stale != self._dir and _NAMESPACE.fullmatch(stale.name):
                    shutil.rmtree(stale, ignore_errors=True)
        answers = self._dir / "answers"
        if not answers.is_dir():
            return
        files = sorted(answers.glob("*.json"), key=lambda path: path.stat().st_mtime)
        for path in files[-self._max :]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._remember(path.stem, CachedReply(**data))
            except (OSError, ValueError, TypeError):
                path.unlink(missing_ok=True)
        if self._replies:
            logger.info("Answer cache: %d answers loaded from disk", len(self._replies))
