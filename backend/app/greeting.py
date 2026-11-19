"""Static greeting audio: the profile intro spoken once per language with the configured
ElevenLabs voice, saved as `frontend/public/audio/greeting-{en,ar}.mp3` and served to every
visitor as a static file (the greeting never calls ElevenLabs at runtime).

    cd backend && uv run python -m app.greeting           # regenerate only what changed
    cd backend && uv run python -m app.greeting --check   # exit 1 if a file is out of date

`greeting-{en,ar}.json` hold the character timestamps of each clip (for word-by-word
highlighting). `greeting.json` next to the files stores, per language, the caption text and a
hash of (format, spoken text, language, voice id, model). A file is regenerated only when
that hash changes, e.g. after the "Short self-introduction" in
knowledge_base/profile/about.md is edited or the voice changes.
tests/test_greeting.py fails when the committed files no longer match the knowledge base.
"""

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

from app.core.config import Settings, get_settings
from app.services.knowledge_service import load_knowledge_service
from app.voice.base import Alignment
from app.voice.text import clean_for_speech

# 2: generated with character timestamps (greeting-{lang}.json) for word highlighting.
GREETING_FORMAT = 2
LANGUAGES = ("en", "ar")
AUDIO_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "audio"
MANIFEST = AUDIO_DIR / "greeting.json"


def voice_for(settings: Settings, language: str) -> str:
    return settings.tts_voice_ar if language == "ar" else settings.tts_voice_en


def greeting_hash(spoken: str, language: str, voice: str, model: str) -> str:
    payload = json.dumps([GREETING_FORMAT, spoken, language, voice, model], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def wanted(settings: Settings) -> dict[str, dict[str, str]]:
    """Per language: the spoken text and its hash, from the current knowledge base."""
    knowledge = load_knowledge_service(settings.knowledge_base_dir)
    if knowledge is None or knowledge.profile is None:
        raise SystemExit("Knowledge base (profile intro) failed to load")
    intro = knowledge.profile.intro
    result = {}
    for language in LANGUAGES:
        spoken = clean_for_speech(getattr(intro, language), language)  # as /voice/speak does
        voice = voice_for(settings, language)
        result[language] = {
            "text": getattr(intro, language),  # shown with the audio (the caption)
            "spoken": spoken,
            "hash": greeting_hash(spoken, language, voice, settings.tts_model),
        }
    return result


def read_manifest() -> dict:
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def stale_languages(settings: Settings) -> list[str]:
    manifest = read_manifest()
    return [
        language
        for language, item in wanted(settings).items()
        if manifest.get(language, {}).get("hash") != item["hash"]
        or not (AUDIO_DIR / f"greeting-{language}.mp3").is_file()
        or not (AUDIO_DIR / f"greeting-{language}.json").is_file()
    ]


async def synthesize(settings: Settings, spoken: str, language: str) -> tuple[bytes, Alignment]:
    from app.voice.factory import build_tts

    tts = build_tts(settings.model_copy(update={"tts_provider": "elevenlabs"}))
    assert tts is not None
    audio = bytearray()
    alignment = Alignment([], [], [])
    try:
        async for chunk in tts.stream_timed(spoken, language=language):
            audio += chunk.audio
            if chunk.alignment:
                print(  # how the provider times its chunks (absolute vs chunk-relative)
                    f"  chunk: {len(chunk.audio)} bytes, chars {len(chunk.alignment.chars)}, "
                    f"{chunk.alignment.starts[0]:.2f}–{chunk.alignment.ends[-1]:.2f} s"
                )
                alignment.extend(chunk.alignment)
    finally:
        await tts.aclose()
    return bytes(audio), alignment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.greeting", description=__doc__)
    parser.add_argument("--check", action="store_true", help="only report stale files")
    parser.add_argument("--force", action="store_true", help="regenerate both languages")
    args = parser.parse_args(argv)
    settings = get_settings()
    stale = list(LANGUAGES) if args.force else stale_languages(settings)
    targets = wanted(settings)
    manifest = read_manifest()
    texts_stale = [
        lang for lang in LANGUAGES if manifest.get(lang, {}).get("text") != targets[lang]["text"]
    ]
    if args.check:
        problems = sorted(set(stale + texts_stale))
        print("Greeting audio up to date" if not problems else f"Stale greeting: {problems}")
        return 1 if problems else 0
    # The caption text is always kept in sync (no ElevenLabs call needed for it).
    for language in LANGUAGES:
        manifest.setdefault(language, {})["text"] = targets[language]["text"]
    if not stale:
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print("Greeting audio up to date; caption texts synced (no ElevenLabs call).")
        return 0
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    for language in stale:
        item = targets[language]
        audio, alignment = asyncio.run(synthesize(settings, item["spoken"], language))
        (AUDIO_DIR / f"greeting-{language}.mp3").write_bytes(audio)
        timing = {"text": item["text"], "spoken": item["spoken"], "alignment": alignment.to_json()}
        (AUDIO_DIR / f"greeting-{language}.json").write_text(
            json.dumps(timing, ensure_ascii=False) + "\n", "utf-8"
        )
        manifest[language] = {
            "text": item["text"],
            "file": f"greeting-{language}.mp3",
            "hash": item["hash"],
            "voice": voice_for(settings, language),
            "model": settings.tts_model,
            "chars": len(item["spoken"]),
            "bytes": len(audio),
        }
        print(f"greeting-{language}.mp3: {len(item['spoken'])} chars -> {len(audio)} bytes")
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
