from solace.conversation import GENERIC_ERROR, Conversation
from solace.safety import RiskLevel
from tests.conftest import echo_agent, failing, fixed_classifier


async def test_ordinary_message_goes_to_companion(settings):
    conv = Conversation(settings, classify=fixed_classifier(RiskLevel.LOW), respond=echo_agent)
    reply = await conv.send("s1", "I've been feeling lonely")
    assert reply.agent == "Companion"
    assert reply.resources == []


async def test_high_risk_goes_to_crisis_with_resources(settings):
    conv = Conversation(settings, classify=fixed_classifier(RiskLevel.HIGH), respond=echo_agent)
    reply = await conv.send("s1", "I can't do this anymore")
    assert reply.agent == "Crisis Support"
    assert any(r.contact == "1926" for r in reply.resources)


async def test_keywords_override_a_low_llm_rating(settings):
    conv = Conversation(settings, classify=fixed_classifier(RiskLevel.NONE), respond=echo_agent)
    reply = await conv.send("s1", "I want to kill myself")
    assert reply.agent == "Crisis Support"


async def test_classifier_failure_falls_back_to_keywords(settings):
    conv = Conversation(settings, classify=failing, respond=echo_agent)
    reply = await conv.send("s1", "I want to die")
    assert reply.agent == "Crisis Support"


async def test_crisis_never_returns_an_error(settings):
    conv = Conversation(settings, classify=fixed_classifier(RiskLevel.IMMINENT), respond=failing)
    reply = await conv.send("s1", "goodbye")
    assert "1926" in reply.reply
    assert reply.resources


async def test_non_crisis_failure_shows_resources(settings):
    conv = Conversation(settings, classify=fixed_classifier(RiskLevel.NONE), respond=failing)
    reply = await conv.send("s1", "hello")
    assert reply.reply == GENERIC_ERROR
    assert reply.resources


async def test_crisis_mode_is_sticky_until_risk_drops(settings):
    levels = iter([RiskLevel.HIGH, RiskLevel.MODERATE, RiskLevel.LOW])

    async def classify(items):
        from solace.safety import RiskAssessment

        return RiskAssessment(level=next(levels), source="llm")

    conv = Conversation(settings, classify=classify, respond=echo_agent)
    assert (await conv.send("s1", "a")).agent == "Crisis Support"
    assert (await conv.send("s1", "b")).agent == "Crisis Support"
    assert (await conv.send("s1", "c")).agent == "Companion"
