"""Small, always-included identity context, so name/contact questions work even when
retrieval is weak. Built from the profile and contact data (no hard-coded facts)."""

from app.core.tokens import estimate_tokens
from app.models.content import ContactResponse, ProfileResponse

MAX_IDENTITY_TOKENS = 300


def build_identity_context(profile: ProfileResponse | None, contact: ContactResponse | None) -> str:
    if profile is None:
        return ""
    name = profile.name + (f" (Arabic spelling: {profile.name_ar})" if profile.name_ar else "")
    lines = [f"Name: {name}", f"Headline: {profile.headline}"]
    if profile.location:
        lines.append(f"Location: {profile.location}")
    if contact and contact.links:
        links = "; ".join(
            f"{link.label}: {link.url.removeprefix('mailto:')}" for link in contact.links
        )
        lines.append(f"Public contact: {links}")
    # The first summary paragraph, shortened by sentences if needed to stay within budget.
    summary = profile.summary_markdown.split("\n\n")[0].strip()
    sentences = summary.split(". ")
    while sentences:
        candidate = "\n".join([*lines, "Summary: " + ". ".join(sentences).rstrip(".") + "."])
        if estimate_tokens(candidate) <= MAX_IDENTITY_TOKENS:
            return candidate
        sentences.pop()
    return "\n".join(lines)
