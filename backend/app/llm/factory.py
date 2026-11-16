from app.core.config import Settings
from app.llm.anthropic import AnthropicProvider
from app.llm.base import LLMConfigError, LLMProvider
from app.llm.fake import FakeProvider
from app.llm.openai_compatible import OpenAICompatibleProvider


def build_provider(settings: Settings) -> LLMProvider:
    """Build the configured provider. Raises LLMConfigError naming the missing setting."""
    key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None

    if settings.llm_provider == "fake":
        return FakeProvider(delay=settings.llm_fake_delay_ms / 1000)

    if not settings.llm_model:
        raise LLMConfigError("LLM_MODEL is required")

    if settings.llm_provider == "openai_compatible":
        if not settings.llm_base_url:
            raise LLMConfigError("LLM_BASE_URL is required for openai_compatible")
        # The key is optional here so local servers such as Ollama work without one.
        return OpenAICompatibleProvider(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=key,
            fallback_model=settings.llm_fallback_model,
            reasoning_effort=settings.llm_reasoning_effort,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    if not key:
        raise LLMConfigError("LLM_API_KEY is required for anthropic")
    return AnthropicProvider(
        api_key=key,
        model=settings.llm_model,
        base_url=settings.llm_base_url or "https://api.anthropic.com",
        timeout_seconds=settings.llm_timeout_seconds,
    )
