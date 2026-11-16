import re
from typing import Literal

Language = Literal["en", "ar"]

_WORD = re.compile(r"[^\W\d_]+")
_ARABIC = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")

# Share of Arabic-script words above which a message counts as Arabic. Counting words (not
# letters) keeps "شو خبرته في FastAPI و Docker؟" Arabic despite the long English terms.
ARABIC_WORD_RATIO = 0.4


def detect_language(text: str, fallback: Language) -> Language:
    words = _WORD.findall(text)
    if not words:
        return fallback
    arabic = sum(1 for word in words if _ARABIC.search(word))
    return "ar" if arabic / len(words) >= ARABIC_WORD_RATIO else "en"
