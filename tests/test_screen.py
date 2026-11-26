import pytest

from solace.safety import RiskLevel, keyword_screen

# A false alarm costs a gentle check-in; a miss can cost a life. Add cases here freely.
CASES = [
    ("I had a nice day at the beach", RiskLevel.NONE),
    ("work is stressful and I'm tired", RiskLevel.NONE),
    ("I feel hopeless, nothing ever changes", RiskLevel.MODERATE),
    ("sometimes I wish I wasn't born", RiskLevel.MODERATE),
    ("everyone would be better off without me", RiskLevel.MODERATE),
    ("I keep thinking about suicide", RiskLevel.HIGH),
    ("I want to die", RiskLevel.HIGH),
    ("I don't want to live anymore", RiskLevel.HIGH),
    ("I've been cutting myself again", RiskLevel.HIGH),
    ("I want to end it all", RiskLevel.HIGH),
    ("I saved up pills to end it", RiskLevel.IMMINENT),
    ("I'm going to kill myself tonight", RiskLevel.IMMINENT),
    ("this is my goodbye", RiskLevel.IMMINENT),
]


@pytest.mark.parametrize(("text", "expected"), CASES)
def test_keyword_screen(text, expected):
    assert keyword_screen(text).level == expected


@pytest.mark.parametrize(
    "text", ["I'll end it this weekend", "tonight I will die", "kms", "i want to unalive"]
)
def test_more_risky_phrasings_are_caught(text):
    assert keyword_screen(text).level >= RiskLevel.HIGH
