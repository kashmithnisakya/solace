"""Deterministic keyword screen.

This runs on every message, even when the LLM is unavailable. It is intentionally
broad: a false alarm costs a gentle check-in, a miss can cost a life.
"""

import re

from solace.safety.risk import RiskAssessment, RiskLevel

_TIME = r"(tonight|today|right now|this (morning|evening|weekend)|after (this|i send))"
_ACT = r"(kill|end|die|suicide)"

_PATTERNS: list[tuple[RiskLevel, str, str]] = [
    # (level, reason, regex)
    (
        RiskLevel.IMMINENT,
        "mentions a plan or method",
        r"\b(overdose|hang (myself|me)|jump (off|from)|slit my|pills? to (die|end)|rope|noose)\b",
    ),
    (RiskLevel.IMMINENT, "mentions timing", rf"\b{_TIME}\b.*\b{_ACT}|\b{_ACT}\w*\b.*\b{_TIME}\b"),
    (
        RiskLevel.IMMINENT,
        "says goodbye",
        r"\b(this is (my )?goodbye|goodbye forever|won'?t be here tomorrow|my last (message|night))\b",
    ),
    (
        RiskLevel.HIGH,
        "talks about suicide",
        r"\b(suicid\w*|kill (myself|me)|end (my|it all|my life)|take my (own )?life|unalive|kms)\b",
    ),
    (
        RiskLevel.HIGH,
        "wants to die",
        r"\b(want(ed)? to die|wanna die|better off dead|don'?t want to (live|be alive))\b",
    ),
    (
        RiskLevel.HIGH,
        "talks about self-harm",
        r"\b(self[- ]?harm|cut(ting)? myself|hurt(ing)? myself|burn(ing)? myself)\b",
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

_COMPILED = [(level, reason, re.compile(rx, re.IGNORECASE)) for level, reason, rx in _PATTERNS]


def keyword_screen(text: str) -> RiskAssessment:
    hits = [(level, reason) for level, reason, rx in _COMPILED if rx.search(text)]
    if not hits:
        return RiskAssessment(source="keywords")
    level = max(level for level, _ in hits)
    return RiskAssessment(level=level, reasons=[reason for _, reason in hits], source="keywords")
