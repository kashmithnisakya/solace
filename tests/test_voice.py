from fastapi.testclient import TestClient

from solace import api
from solace.safety import RiskLevel
from solace.voice import session_config
from tests.conftest import fixed_classifier, make_conversation

SID = "a" * 32


def voice_client(settings, level=RiskLevel.NONE, mint_fails=False):
    api._conversation = make_conversation(settings, level)
    for limiter in (api.chat_limiter, api.voice_call_limiter, api.voice_turn_limiter):
        limiter.hits.clear()
    minted: list[dict] = []

    async def mint(session):
        if mint_fails:
            raise RuntimeError("down")
        minted.append(session)
        return {"value": "ek_test", "expires_at": 123}

    api.voice_mint = mint
    return TestClient(api.app), minted


def test_session_config_is_speech_ready(settings):
    cfg = session_config(settings, "be kind")
    assert cfg["type"] == "realtime" and cfg["instructions"] == "be kind"
    assert cfg["audio"]["input"]["transcription"]["language"] == "en"
    assert cfg["audio"]["input"]["turn_detection"]["type"] == "semantic_vad"


def test_voice_session_mints_short_lived_key_with_spoken_instructions(settings):
    c, minted = voice_client(settings)
    body = c.post("/api/voice/session", json={}).json()
    assert body["client_secret"] == "ek_test" and len(body["session_id"]) == 32
    assert body["resources"]
    assert "speaking out loud" in minted[0]["instructions"]
    assert "Companion" not in minted[0]["instructions"]  # instructions, not an agent name
    assert "OPENAI" not in str(body)


def test_voice_session_reports_unavailable_when_minting_fails(settings):
    c, _ = voice_client(settings, mint_fails=True)
    assert c.post("/api/voice/session", json={}).json()["detail"] == "voice_unavailable"


def test_spoken_turns_are_saved_and_screened(settings):
    c, _ = voice_client(settings)
    turn = c.post(
        "/api/voice/turn", json={"session_id": SID, "role": "user", "text": "exams are stressing me"}
    )
    assert turn.json()["in_crisis"] is False
    assert (
        c.post(
            "/api/voice/turn", json={"session_id": SID, "role": "assistant", "text": "That's a lot."}
        ).status_code
        == 204
    )
    msgs = c.get(f"/api/sessions/{SID}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["text"] == "exams are stressing me"


def test_spoken_crisis_switches_to_crisis_instructions_with_numbers(settings):
    c, _ = voice_client(settings)
    body = c.post(
        "/api/voice/turn",
        json={"session_id": SID, "role": "user", "text": "I'm going to kill myself tonight"},
    ).json()
    assert body["in_crisis"] is True and body["risk_level"] == "imminent"
    assert body["agent"] == "Crisis Support"
    assert "1926" in body["instructions"] and "digit by digit" in body["instructions"]
    assert body["resources"]


async def test_new_call_resumes_in_crisis_mode_and_remembers_text_chat(settings):
    conv = make_conversation(settings, classify=fixed_classifier(RiskLevel.HIGH))
    await conv.voice_user(SID, "I don't want to be here anymore")
    instructions = await conv.voice_start(SID)
    assert "crisis-support mode" in instructions
    assert "I don't want to be here anymore" in instructions


def test_voice_turn_validates_input(settings):
    c, _ = voice_client(settings)
    assert (
        c.post("/api/voice/turn", json={"session_id": "x", "role": "user", "text": "hi"}).status_code == 422
    )
    assert (
        c.post("/api/voice/turn", json={"session_id": SID, "role": "system", "text": "hi"}).status_code == 422
    )
    assert c.post("/api/voice/turn", json={"session_id": SID, "role": "user", "text": ""}).status_code == 422


def test_voice_calls_are_rate_limited_with_help_included(settings):
    c, _ = voice_client(settings)
    codes = [c.post("/api/voice/session", json={}).status_code for _ in range(7)]
    assert codes[-1] == 429
    assert c.post("/api/voice/session", json={}).json()["resources"]


def test_csp_allows_openai_realtime(settings):
    c, _ = voice_client(settings)
    assert "connect-src 'self' https://api.openai.com" in c.get("/").headers["content-security-policy"]
