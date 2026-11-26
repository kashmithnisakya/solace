from fastapi.testclient import TestClient

from solace import api
from solace.conversation import Conversation
from solace.safety import RiskLevel
from tests.conftest import echo_agent, fixed_classifier


def client(settings, level=RiskLevel.NONE):
    api._conversation = Conversation(settings, classify=fixed_classifier(level), respond=echo_agent)
    return TestClient(api.app)


def test_health(settings):
    assert client(settings).get("/health").json()["status"] == "ok"


def test_chat_creates_session_and_ignores_unknown_faith(settings):
    res = client(settings).post("/api/chat", json={"message": "hi", "faith": "made-up"})
    body = res.json()
    assert res.status_code == 200
    assert body["session_id"]
    assert body["agent"] == "Companion"


def test_chat_rejects_empty_message(settings):
    assert client(settings).post("/api/chat", json={"message": ""}).status_code == 422


def test_index_page(settings):
    assert "Solace" in client(settings).get("/").text
