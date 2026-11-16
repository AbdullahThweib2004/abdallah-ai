def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 characters per token); real counts come from provider usage."""
    return max(1, round(len(text) / 4))
