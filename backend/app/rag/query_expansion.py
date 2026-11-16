"""Arabic → English query expansion for keyword (BM25) search over English documents.

Two sources: the knowledge base glossary (names: نواة → Nawa, بنك فلسطين → Bank of Palestine)
and a small table of generic Arabic vocabulary (not facts about anyone).
"""

import re
from collections.abc import Sequence

from app.knowledge.loader import KnowledgeDocument
from app.knowledge.schemas import GlossaryMeta

_DIACRITICS = re.compile(r"[ً-ٰٟـ]")
_ARABIC = re.compile(r"[؀-ۿ]")
_PARENS = re.compile(r"\([^)]*\)")
_TABLE_ROW = re.compile(r"^\|(.+)\|\s*$")

# Generic vocabulary, normalized (ة→ه, أ/إ/آ→ا). Matched inside longer words too, so
# "بمشروع" and "المهارات" hit "مشروع" and "مهارات".
COMMON_TERMS: dict[str, str] = {
    "مشروع": "project",
    "مشاريع": "projects",
    "بنك": "bank",
    "مصرف": "banking",
    "تدريب": "training internship",
    "متدرب": "intern training",
    "خبره": "experience",
    "مهارات": "skills",
    "مهاره": "skill",
    "تعليم": "education",
    "جامعه": "university",
    "دراسه": "study degree",
    "شهاده": "degree",
    "تخرج": "graduation project",
    "تواصل": "contact",
    "بريد": "email",
    "ايميل": "email",
    "لغات": "languages",
    "اهتمامات": "interests",
    "اهداف": "goals career direction",
    "اداء": "performance results",
    "سرعه": "latency throughput performance",
    "نتائج": "results",
    "تقنيات": "technologies",
    "امن": "security",
    "حمايه": "security",
    "وكلاء": "agents",
    "وكيل": "agent",
    "مساعد": "assistant",
    "مستندات": "documents",
    "محرك": "engine",
    "استدلال": "inference",
    "اقسام": "departments",
    "قسم": "department",
    "مسؤوليات": "responsibilities",
    "مسووليات": "responsibilities",
    "معماريه": "architecture",
    "بنيه": "architecture",
    "تحديات": "challenges",
    "قيود": "limitations",
    "مساهمه": "contribution",
}


def normalize_arabic(text: str) -> str:
    text = _DIACRITICS.sub("", text.lower())
    return (
        text.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ة", "ه")
        .replace("ى", "ي")
    )


def glossary_terms(documents: Sequence[KnowledgeDocument]) -> dict[str, str]:
    """Normalized Arabic term → English term, from the glossary tables (`| English | Arabic |`)."""
    terms: dict[str, str] = {}
    for document in documents:
        if not isinstance(document.meta, GlossaryMeta) or document.meta.status != "approved":
            continue
        for section in document.sections:
            for line in section.content.splitlines():
                match = _TABLE_ROW.match(line.strip())
                if not match:
                    continue
                cells = [cell.strip() for cell in match.group(1).split("|")]
                if len(cells) < 2:
                    continue
                english, arabic = (
                    _PARENS.sub("", cells[0]).strip(),
                    _PARENS.sub("", cells[1]).strip(),
                )
                if english and arabic and _ARABIC.search(arabic):
                    terms[normalize_arabic(arabic)] = english
    return terms


def expand_query(query: str, glossary: dict[str, str]) -> str:
    """Append English equivalents of Arabic terms found in the query (no-op for English)."""
    if not _ARABIC.search(query):
        return query
    normalized = normalize_arabic(query)
    additions: list[str] = []
    for arabic, english in [*glossary.items(), *COMMON_TERMS.items()]:
        if arabic in normalized and english not in additions:
            additions.append(english)
    return f"{query} {' '.join(additions)}" if additions else query
