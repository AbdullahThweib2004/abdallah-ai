from app.core.config import Settings
from app.voice.base import STTProvider, TTSProvider, VoiceConfigError
from app.voice.elevenlabs import ElevenLabsTTS
from app.voice.fake import FakeSTT, FakeTTS
from app.voice.whisper import WhisperSTT


def build_stt(settings: Settings) -> STTProvider:
    """Build the configured STT provider. Raises VoiceConfigError naming the missing setting."""
    if settings.stt_provider == "fake":
        return FakeSTT()
    if not settings.llm_base_url:
        raise VoiceConfigError("LLM_BASE_URL is required for STT_PROVIDER=groq")
    if not settings.llm_api_key:
        raise VoiceConfigError("LLM_API_KEY is required for STT_PROVIDER=groq")
    return WhisperSTT(
        base_url=settings.llm_base_url,
        model=settings.stt_model,
        api_key=settings.llm_api_key.get_secret_value(),
        timeout_seconds=settings.stt_timeout_seconds,
    )


def build_tts(settings: Settings) -> TTSProvider | None:
    """Build the server-side TTS provider; None means the browser speaks (`browser`)."""
    if settings.tts_provider == "browser":
        return None
    if settings.tts_provider == "fake":
        return FakeTTS()
    if not settings.elevenlabs_api_key:
        raise VoiceConfigError("ELEVENLABS_API_KEY is required for TTS_PROVIDER=elevenlabs")
    return ElevenLabsTTS(
        api_key=settings.elevenlabs_api_key.get_secret_value(),
        model=settings.tts_model,
        voices={"en": settings.tts_voice_en, "ar": settings.tts_voice_ar},
        timeout_seconds=settings.tts_timeout_seconds,
    )
