"""Friendly, provider-neutral messages for chat errors and limits (EN/AR)."""

from typing import Literal

ErrorCode = Literal["unavailable", "timeout", "busy"]
LimitCode = Literal["rate_limited", "daily_limit", "daily_cap"]

MESSAGES: dict[str, dict[str, str]] = {
    "unavailable": {
        "en": "Abdallah AI can't answer right now. Please try again in a moment.",
        "ar": "لا يستطيع Abdallah AI الإجابة الآن. يرجى المحاولة مرة أخرى بعد قليل.",
    },
    "timeout": {
        "en": "Abdallah AI took too long to answer. Please try again.",
        "ar": "استغرق Abdallah AI وقتاً طويلاً للإجابة. يرجى المحاولة مرة أخرى.",
    },
    "busy": {
        "en": (
            "Abdallah AI is answering a lot of questions right now. Please try again in a minute."
        ),
        "ar": "يجيب Abdallah AI عن أسئلة كثيرة الآن. يرجى المحاولة مرة أخرى بعد دقيقة.",
    },
    "rate_limited": {
        "en": "You're sending messages quite fast. Please wait a minute and try again.",
        "ar": "أنت ترسل الرسائل بسرعة كبيرة. يرجى الانتظار دقيقة ثم المحاولة مرة أخرى.",
    },
    "daily_limit": {
        "en": (
            "You've reached today's message limit. Please come back tomorrow, "
            "or contact Abdallah directly by email or LinkedIn."
        ),
        "ar": (
            "لقد وصلت إلى الحد اليومي للرسائل. يرجى العودة غداً، "
            "أو التواصل مع عبدالله مباشرة عبر البريد الإلكتروني أو LinkedIn."
        ),
    },
    "daily_cap": {
        "en": (
            "Abdallah AI has reached its daily conversation limit. Please come back tomorrow, "
            "or contact Abdallah by email or LinkedIn."
        ),
        "ar": (
            "وصل Abdallah AI إلى حدّه اليومي من المحادثات. يرجى العودة غداً، "
            "أو التواصل مع عبدالله عبر البريد الإلكتروني أو LinkedIn."
        ),
    },
}


def message(code: str, language: str) -> str:
    return MESSAGES[code]["ar" if language == "ar" else "en"]
