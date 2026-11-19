"""The committed greeting audio must match the knowledge base intro and the configured voice."""

from pathlib import Path

from app.core.config import Settings
from app.greeting import AUDIO_DIR, LANGUAGES, greeting_hash, read_manifest, wanted

REPO_KB = Path(__file__).resolve().parents[2] / "knowledge_base"


def test_committed_greeting_files_match_the_intro_and_voice() -> None:
    settings = Settings(_env_file=None, knowledge_base_dir=REPO_KB)  # defaults: the stock voice
    manifest = read_manifest()
    for language, item in wanted(settings).items():
        assert manifest[language]["hash"] == item["hash"], (
            f"greeting-{language}.mp3 is stale: run `uv run python -m app.greeting`"
        )
        assert (AUDIO_DIR / f"greeting-{language}.mp3").stat().st_size > 10_000


def test_hash_changes_with_text_voice_and_model() -> None:
    base = greeting_hash("Hi.", "en", "voice", "model")
    assert greeting_hash("Hello.", "en", "voice", "model") != base
    assert greeting_hash("Hi.", "ar", "voice", "model") != base
    assert greeting_hash("Hi.", "en", "other", "model") != base
    assert greeting_hash("Hi.", "en", "voice", "other") != base
    assert set(LANGUAGES) == {"en", "ar"}
