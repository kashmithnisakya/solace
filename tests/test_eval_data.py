"""Offline safety checks that run in CI on every change, using the evaluation datasets.

The live evaluation (`python -m evals`) also tests the AI screener and replies. These checks only
cover what must hold without any AI: the keyword screen, and that the datasets are well formed.
"""

import pytest

from evals import LEVELS, load
from evals.judge import CRITERIA, hard_checks
from solace.safety import RiskLevel, keyword_screen

RISK = load("risk_cases.json")
REPLIES = load("reply_scenarios.json")


def test_risk_cases_are_well_formed():
    ids = [c["id"] for c in RISK]
    assert len(ids) == len(set(ids))
    for c in RISK:
        assert c["min"] in LEVELS and c["max"] in LEVELS, c["id"]
        assert LEVELS.index(c["min"]) <= LEVELS.index(c["max"]), c["id"]
        assert c["text"].strip() and c["tags"], c["id"]


def test_reply_scenarios_are_well_formed():
    ids = [s["id"] for s in REPLIES]
    assert len(ids) == len(set(ids))
    for s in REPLIES:
        assert s["turns"] and s["agent"] in {"crisis", "companion", "any"}, s["id"]
        assert set(s["criteria"]) <= set(CRITERIA), s["id"]


@pytest.mark.parametrize("case", [c for c in RISK if "explicit" in c["tags"]], ids=lambda c: c["id"])
def test_keyword_screen_catches_explicit_risk_on_its_own(case):
    # These must be caught even if the AI screener is down.
    assert keyword_screen(case["text"]).level >= RiskLevel[case["min"].upper()]


@pytest.mark.parametrize("case", [c for c in RISK if "benign" in c["tags"]], ids=lambda c: c["id"])
def test_keyword_screen_does_not_alarm_on_figures_of_speech(case):
    assert keyword_screen(case["text"]).level <= RiskLevel[case["max"].upper()]


def test_hard_checks_catch_doses_and_extra_questions():
    out = hard_checks(["Taking 20 tablets would be dangerous."], ["no_method_info"], ["1926"])
    assert out["no_method_info"][0] is False
    out = hard_checks(["How are you? What happened? Why?"], ["one_question_max"], ["1926"])
    assert out["one_question_max"][0] is False
    out = hard_checks(
        ["Please call 1926 now."], ["gives_crisis_line", "no_unprompted_crisis_numbers"], ["1926"]
    )
    assert out["gives_crisis_line"][0] is True and out["no_unprompted_crisis_numbers"][0] is False
