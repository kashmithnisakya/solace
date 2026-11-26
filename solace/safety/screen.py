"""Deterministic keyword screen.

This runs on every message, even when the LLM is unavailable. It is intentionally
broad: a false alarm costs a gentle check-in, a miss can cost a life.
"""

import re

from solace.safety.risk import RiskAssessment, RiskLevel

_TIME = r"(tonight|today|right now|this (morning|evening|weekend)|after (this|i send))"
# Talk about suicide itself, not about prevention work or statistics.
_SUICIDE = r"suicid(e|al)\w*(?!\s+(prevention|awareness|hotline|helpline|line|rates?|statistics|research))"
# Ending one's own life. "end it with my boyfriend" or "end my shift" are not.
_END = r"end(ing)?\s+(it(\s+all)?(?!\s+with)|my (own )?life|myself|everything|things)\b"
_ACT = rf"(kill(ing)? (myself|me)|{_END}|die\b|{_SUICIDE}|kms|unalive)"

_PATTERNS: list[tuple[RiskLevel, str, str]] = [
    # (level, reason, regex)
    (
        RiskLevel.IMMINENT,
        "mentions a plan or method",
        r"\b(overdose|hang (myself|me)|jump (off|from)|slit my|pills? to (die|end)|noose"
        r"|(bought|got|have|tied?|tying) (a |the )?rope)\b",
    ),
    (RiskLevel.IMMINENT, "mentions timing", rf"\b{_TIME}\b.*\b{_ACT}|\b{_ACT}.*\b{_TIME}\b"),
    (
        RiskLevel.IMMINENT,
        "says goodbye",
        r"\b(this is (my )?goodbye|goodbye forever|won'?t be here tomorrow|my last (message|night))\b",
    ),
    (
        RiskLevel.HIGH,
        "talks about suicide",
        rf"\b({_SUICIDE}|kill (myself|me)|{_END}|take my (own )?life|unalive|kms)",
    ),
    (
        RiskLevel.HIGH,
        "wants to die",
        r"\b(want(ed)? to die|wanna die|better off dead|don'?t want to (live|be alive)"
        r"|don'?t want to (be here|exist|wake up) any ?more)\b",
    ),
    (
        RiskLevel.HIGH,
        "talks about self-harm",
        r"\b(self[- ]?harm|cut(ting)? myself|hurt(ing)? myself|burn(ing)? myself)\b",
    ),
    # Sinhala, in script and romanised ("Singlish"). Figures of speech such as "විභාගේ මාව මරනවා"
    # (the exam is killing me) or "හිනා වෙලා මැරෙනවා" (dying of laughter) deliberately don't match.
    (
        RiskLevel.IMMINENT,
        "mentions a plan, method or timing (Sinhala)",
        r"(වහ බොන්න|පෙති ගොඩක් (බොන්න|බිව්වා|බීලා)|සදහටම සමු|අද (රෑ|රෑට) .*(මැරෙන්න|මරාගන්න)"
        r"|\bwaha (bonna|biwwa)\b|\bpethi godak (bonna|biwwa|beela)\b|\bsadahatama samu"
        r"|\bada (ra|raa|reta|rata)\b.*\b(marenna|maraganna|mara ganna)\b)",
    ),
    (
        RiskLevel.HIGH,
        "talks about suicide or dying (Sinhala)",
        r"(සියදිවි|සිය දිවි|මැරෙන්න (හිතෙනවා|ඕනේ|ඕන|හිතුණා)|මැරිලා යන්න|මරා ?ගන්න|ජීවිතේ නැති කර"
        r"|ජීවත් වෙන්න (ඕනේ|ඕන) නෑ|මැරුණොත් හොඳයි|තුවාල කර ගන්න|අත කපා ?ගත්තා"
        r"|\bsiya ?di[wv]i|\bmarenna (hithenawa|hithenwa|hithuna|one|ona|oney)\b|\bmarila yanna\b"
        r"|\bmara ?ganna\b|\bjeewithe nathi kara|\bjeewath (wenna|venna) (one|ona) na\b"
        r"|\bmarunoth hondai\b|\batha kapa ?gaththa\b)",
    ),
    (
        RiskLevel.MODERATE,
        "hopeless or tired of living (Sinhala)",
        r"(ජීවත් වෙන්න එපා|ජීවිතේ එපා|බලාපොරොත්තුවක් නෑ|හැමෝටම බරක්|කිසිම තේරුමක් නෑ"
        r"|\bjeewath (wenna|venna) epa\b|\bjeewithe epa\b|\bbalaporoththuwak na\b|\bhamotama barak\b)",
    ),
    (
        RiskLevel.MODERATE,
        "feels hopeless",
        r"\b(no (point|reason) (in )?(living|going on)|can'?t go on|no way out|hopeless"
        r"|give up on (life|everything))\b",
    ),
    (
        RiskLevel.MODERATE,
        "wishes to disappear",
        r"\b(disappear forever|not wake up|wish i (was|were)n'?t (here|born|alive)"
        r"|everyone would be better off)\b",
    ),
]

# "I'm not suicidal", "I would never hurt myself": a negation right before the phrase.
# Only these reasons can be cancelled, and only by a negation directly in front, so
# "I can't stop thinking about suicide" still counts. The AI screener still checks every message.
_NEGATABLE = {"talks about suicide", "talks about self-harm"}
_NEGATION = re.compile(r"\b(not|never|n't)\s+((really|ever|be|feeling|going to|gonna)\s+)?$", re.IGNORECASE)

_COMPILED = [(level, reason, re.compile(rx, re.IGNORECASE)) for level, reason, rx in _PATTERNS]


def _matches(reason: str, rx: re.Pattern, text: str) -> bool:
    for m in rx.finditer(text):
        if reason in _NEGATABLE and _NEGATION.search(text[: m.start()]):
            continue
        return True
    return False


def keyword_screen(text: str) -> RiskAssessment:
    hits = [(level, reason) for level, reason, rx in _COMPILED if _matches(reason, rx, text)]
    if not hits:
        return RiskAssessment(source="keywords")
    level = max(level for level, _ in hits)
    return RiskAssessment(level=level, reasons=[reason for _, reason in hits], source="keywords")
