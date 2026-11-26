import pytest
from agents import RunContextWrapper
from fastapi.testclient import TestClient

from solace import api, i18n
from solace.assistants.companion import build_companion, companion_instructions
from solace.assistants.context import UserContext
from solace.assistants.crisis import fallback_crisis_message
from solace.safety import RiskLevel, keyword_screen, resources_for
from solace.voice import session_config
from tests.conftest import failing, make_conversation

SID = "d" * 32


def test_detects_sinhala_script_but_leaves_latin_to_the_chosen_language():
    assert i18n.detect("මට හරි දුකයි") == "si"
    assert i18n.detect("exam එක ගැන stress") == "si"  # mostly Sinhala, with everyday English words
    assert i18n.detect("I feel sad") is None
    assert i18n.detect("mata hari dukai") is None  # romanised: could be either, so the choice decides
    assert i18n.reply_language("si", "ok") == "si"
    assert i18n.reply_language("en", "මට හරි දුකයි") == "si"
    assert i18n.reply_language("xx", "") == "en"


def test_crisis_lines_in_sinhala_keep_the_same_numbers():
    en, si = resources_for("LK"), resources_for("LK", "si")
    assert [r.contact for r in en] == [r.contact for r in si]
    assert si[0].name.startswith("ජාතික") and si[0].hours == "පැය 24 පුරා"
    assert en[0].name == "National Mental Health Helpline"


def test_fallback_crisis_message_in_sinhala_still_has_the_numbers():
    ctx = UserContext(language="si", resources=resources_for("LK", "si"))
    text = fallback_crisis_message(ctx)
    assert "ආරක්ෂිතද" in text and "1926" in text and "119" in text


def test_prompt_follows_the_persons_language():
    agent = build_companion(None)
    si = companion_instructions(RunContextWrapper(context=UserContext(language="si")), agent)
    assert "app language is Sinhala" in si and "ඔයා" in si
    en = companion_instructions(RunContextWrapper(context=UserContext()), agent)
    assert "app language is English" in en


async def test_sinhala_message_gets_sinhala_help_and_error_text(settings):
    conv = make_conversation(settings, RiskLevel.HIGH, respond=failing)
    reply = await conv.send(SID, "මට මැරෙන්න හිතෙනවා")
    assert reply.agent == "Crisis Support"
    assert "ආරක්ෂිතද" in reply.reply  # the fixed crisis message, in Sinhala
    assert reply.resources[0].name.startswith("ජාතික")

    reply = await make_conversation(settings, respond=failing).send(SID, "hello", lang="si")
    assert reply.reply == i18n.text("generic_error", "si")


def test_api_resources_and_slow_down_in_sinhala(settings):
    api._conversation = make_conversation(settings)
    api.chat_limiter.hits.clear()
    c = TestClient(api.app)
    assert c.get("/api/resources?lang=si").json()[0]["name"].startswith("ජාතික")
    assert c.get("/api/resources?lang=xx").json()[0]["name"] == "National Mental Health Helpline"
    for _ in range(20):
        c.post("/api/chat?lang=si", json={"message": "හායි", "lang": "si"})
    res = c.post("/api/chat?lang=si", json={"message": "හායි", "lang": "si"})
    assert res.status_code == 429
    assert res.json()["message"] == i18n.text("slow_down", "si")
    assert res.json()["resources"][0]["name"].startswith("ජාතික")


def test_voice_uses_a_sinhala_hint_instead_of_an_unsupported_language_code(settings):
    si = session_config(settings, "x", "si")["audio"]["input"]["transcription"]
    assert "language" not in si and "සිංහල" in si["prompt"]
    assert session_config(settings, "x", "en")["audio"]["input"]["transcription"]["language"] == "en"


@pytest.mark.parametrize(
    ("text", "at_least"),
    [
        ("මට මැරෙන්න හිතෙනවා", RiskLevel.HIGH),
        ("mata marenna hithenawa", RiskLevel.HIGH),
        ("මාව මරාගන්න හිතෙනවා", RiskLevel.HIGH),
        ("siyadivi nasa ganna hithenawa", RiskLevel.HIGH),
        ("ජීවත් වෙන්න ඕනේ නෑ", RiskLevel.HIGH),
        ("අද රෑ මම මැරෙන්න යනවා", RiskLevel.IMMINENT),
        ("ada ra mama marenna yanawa", RiskLevel.IMMINENT),
        ("waha bonna hithenawa", RiskLevel.IMMINENT),
        ("jeewath wenna epa wela", RiskLevel.MODERATE),
        ("මම හැමෝටම බරක්", RiskLevel.MODERATE),
    ],
)
def test_sinhala_risk_is_caught_without_ai(text, at_least):
    assert keyword_screen(text).level >= at_least


@pytest.mark.parametrize(
    "text",
    ["විභාගේ මාව මරනවා", "හිනා වෙලා මැරෙනවා", "අද රෑ ෆිල්ම් එකක් බලමු", "mata hari dukai", "phone eka marila"],
)
def test_sinhala_figures_of_speech_are_not_alarms(text):
    assert keyword_screen(text).level <= RiskLevel.LOW
