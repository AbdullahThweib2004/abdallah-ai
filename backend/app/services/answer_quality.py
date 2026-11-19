"""Rule checks that every answer must pass (the prompt's global rules), shared by the chat
evals and the answer cache: an answer that breaks one is never cached, because a cached answer
is replayed to every visitor who asks the same first question."""

import re

# Praise/evaluation words the knowledge base never uses: answers state facts only.
PRAISE_WORDS = [
    "impressive", "deep understanding", "passionate", "passion for", "talented", "exceptional",
    "outstanding", "remarkable", "brilliant", "highly skilled", "showcases his",
    "شغف", "مبهر", "رائع", "متميز", "استثنائي", "موهوب", "مذهل", "فهم عميق", "عبقري",
]  # fmt: skip
# Known Arabic mistakes: the name must be the one word عبدالله; jussive of بُني is تُبنَ.
ARABIC_MISTAKES = ["عبد الله", "لم تُبنى"]

_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670\u0640]")
_HYPHENS = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2212]")
_SPACES = re.compile(r"[\u00A0\u202F\u2009\u200A]")
# Plain text only: shown as subtitles and spoken.
_MARKDOWN = re.compile(
    r"\*\*|__|```|^\s*#{1,6}\s|^\s*[-*•]\s|^\s*\d+\.\s|^\s*\|.*\|\s*$", re.MULTILINE
)
# A Latin letter directly touching an Arabic LETTER ("endorsه", "وReact", "بـMCP"). Arabic
# punctuation such as "،" after an English word is fine.
_AR_LETTER = "[\u0621-\u064a\u0671-\u06d3]"
_GLUED = re.compile(f"{_AR_LETTER}[A-Za-z]|[A-Za-z]{_AR_LETTER}")
_URL = re.compile(r"https?://|www\.")
# Unfilled template text copied from a prompt ("<project name>", "<technology>").
_PLACEHOLDER = re.compile(r"<[^<>]{2,40}>")
# His name is "Abdallah" in sentences; "abdullah" only inside his email address / GitHub
# username (followed by more letters or digits, e.g. "abdullahthweib111").
_MISSPELT_NAME = re.compile(r"\babdullah(?![a-z0-9])|\bthuweb\b", re.IGNORECASE)


def normalize(text: str) -> str:
    text = _SPACES.sub(" ", _HYPHENS.sub("-", _DIACRITICS.sub("", text)))
    return text.casefold().replace("’", "'")


def answer_problems(answer: str) -> list[str]:
    """Human-readable reasons, empty when the answer follows every global rule."""
    if not answer.strip():
        return ["empty answer"]
    text = normalize(answer)
    reasons: list[str] = []
    if _MARKDOWN.search(answer):
        reasons.append("uses markdown")
    reasons += [f"praise {word!r}" for word in PRAISE_WORDS if normalize(word) in text]
    reasons += [f"Arabic mistake {m!r}" for m in ARABIC_MISTAKES if normalize(m) in text]
    if glued := _GLUED.search(answer):
        start = max(glued.start() - 6, 0)
        reasons.append(f"Latin glued to Arabic {answer[start : glued.end() + 6]!r}")
    if _URL.search(answer):
        reasons.append("reads out a URL")
    if placeholder := _PLACEHOLDER.search(answer):
        reasons.append(f"template placeholder {placeholder.group()!r}")
    if name := _MISSPELT_NAME.search(answer):
        reasons.append(f"misspelt name {name.group()!r}")
    return reasons
