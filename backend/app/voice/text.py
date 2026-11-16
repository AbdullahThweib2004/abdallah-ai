"""Turn an answer sentence into text that sounds right when spoken.

URLs, markdown and source labels are dropped; email addresses become "his email" so the
voice never spells out an address. Decimal numbers and terms such as "Node.js" are kept.
"""

import re

from app.voice.base import Language

EMAIL_WORDS: dict[Language, str] = {"en": "his email", "ar": "بريده الإلكتروني"}

_SOURCE_LABEL = re.compile(r"[\[(]\s*(?:source|sources|المصدر|مصدر)\s*:[^\])]*[\])]", re.I)
_CITATION = re.compile(r"\[\d+(?:,\s*\d+)*\]")
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_CODE_FENCE = re.compile(r"```[^\n]*\n?")
_EMAIL = re.compile(r"(?:mailto:)?[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.I)
# A URL never ends in sentence punctuation: "see https://x.io/a." keeps its final period.
_URL_TAIL = r"(?:\S*[^\s.,;:!?)\]،؛؟])?"
_URL = re.compile(r"(?:https?://|www\.)" + _URL_TAIL, re.I)
# Bare domains such as "github.com/user". Lowercase only and a short TLD list, so that
# "Node.js", "ASP.NET" and "97.15" are not mistaken for links.
_BARE_DOMAIN = re.compile(
    r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|dev|ai|app|me|edu|co|ps|gov|info)"
    r"\b(?:/" + _URL_TAIL + ")?"
)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.M)
_QUOTE = re.compile(r"^\s{0,3}>\s?", re.M)
_BULLET = re.compile(r"^\s*[-*+•]\s+", re.M)
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}.*$", re.M)
_EMPHASIS = re.compile(r"(\*\*|__|\*|~~)(?=\S)(.+?)(?<=\S)\1")
_LEFTOVER_MARKS = re.compile(r"[*`#~|]|(?<!\w)_|_(?!\w)")
_EMPTY_BRACKETS = re.compile(r"[(\[]\s*[)\]]")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,!?;:؟،؛])")
_REPEATED_PUNCT = re.compile(r"([.,;:،؛])(?:\s*[.,;:،؛])+")
# "find it at <url>." loses its URL; drop the orphaned preposition too.
_DANGLING_PREP = re.compile(r"\s(?:at|via)\s*([.!?])", re.I)
_SPACES = re.compile(r"\s+")


def clean_for_speech(text: str, language: Language) -> str:
    text = _SOURCE_LABEL.sub(" ", text)
    text = _CITATION.sub(" ", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _CODE_FENCE.sub(" ", text)
    text = _EMAIL.sub(EMAIL_WORDS[language], text)
    text = _URL.sub(" ", text)
    text = _BARE_DOMAIN.sub(" ", text)
    text = _TABLE_RULE.sub(" ", text)
    text = _HEADING.sub("", text)
    text = _QUOTE.sub("", text)
    text = _BULLET.sub("", text)
    text = _EMPHASIS.sub(r"\2", text)
    text = _LEFTOVER_MARKS.sub(" ", text)
    text = _EMPTY_BRACKETS.sub(" ", text)
    text = _SPACES.sub(" ", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _DANGLING_PREP.sub(r"\1", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _REPEATED_PUNCT.sub(r"\1", text)
    text = text.strip(" ,;:،؛")
    # Nothing speakable left (only punctuation or symbols).
    return text if re.search(r"[^\W_]", text) else ""
