"""Languages: English and Sinhala (Tamil next).

Solace replies in the language the person writes in. Their chosen app language is the fallback
when a message doesn't make it clear (for example a short "ok").
"""

import re

LANGUAGES = {"en": "English", "si": "Sinhala"}
DEFAULT = "en"

_SINHALA = re.compile(r"[඀-෿]")


def clean(lang: str | None) -> str:
    return lang if lang in LANGUAGES else DEFAULT


def detect(text: str) -> str | None:
    """'si' when a message is mostly Sinhala script. Latin letters could be English or romanised
    Sinhala, so those are left to the person's chosen language (and the model's judgement)."""
    sinhala = len(_SINHALA.findall(text))
    latin = len(re.findall(r"[A-Za-z]", text))
    # Sri Lankans often mix in English words ("exam එක ගැන stress"): any real Sinhala means Sinhala.
    return "si" if sinhala >= 3 and sinhala >= latin * 0.3 else None


def reply_language(chosen: str | None, message: str = "") -> str:
    return detect(message) or clean(chosen)


TEXTS: dict[str, dict[str, str]] = {
    "generic_error": {
        "en": "I'm sorry, I'm having trouble responding right now. Please try again in a moment. "
        "If you need to talk to someone urgently, the support lines below are free and confidential.",
        "si": "සමාවෙන්න, මට දැන් උත්තර දෙන්න අමාරුයි. පොඩ්ඩකින් ආයෙත් උත්සාහ කරන්න. "
        "ඉක්මනින් කාට හරි කතා කරන්න ඕනේ නම්, පහළ තියෙන සහාය අංක නොමිලේ, රහසිගතයි.",
    },
    "slow_down": {
        "en": "You're sending messages quickly. Take a breath, and try again in a minute.",
        "si": "ඔයා ගොඩක් ඉක්මනින් පණිවිඩ එවනවා. පොඩ්ඩක් හුස්ම අරගෙන, විනාඩියකින් ආයෙත් උත්සාහ කරන්න.",
    },
    "fallback_crisis": {
        "en": "I'm really glad you told me, and I'm worried about you. You deserve support from a real "
        "person right now. Please reach out to one of these, they are free and confidential:\n"
        "{resources}\n"
        "If you are in immediate danger, please call emergency services now. Are you safe right now?",
        "si": "ඔයා මට මේ ගැන කිව්වට මම ගොඩක් සතුටුයි, ඒ වගේම මට ඔයා ගැන කනස්සල්ලක් තියෙනවා. "
        "ඔයාට දැන්ම ඇත්ත මනුස්සයෙක්ගේ සහාය ලැබෙන්න ඕනේ. කරුණාකරලා මේ එකකට කතා කරන්න, "
        "ඒවා නොමිලේ, රහසිගතයි:\n"
        "{resources}\n"
        "ඔයා දැන්ම අනතුරක ඉන්නවා නම්, කරුණාකරලා වහාම හදිසි සේවාවලට කතා කරන්න. ඔයා දැන් ආරක්ෂිතද?",
    },
}


def text(key: str, lang: str | None, **values: str) -> str:
    template = TEXTS[key].get(clean(lang)) or TEXTS[key][DEFAULT]
    return template.format(**values) if values else template
