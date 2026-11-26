from fastapi.testclient import TestClient

from solace import api
from solace.safety import RiskLevel
from tests.conftest import make_conversation


def client(settings, level=RiskLevel.NONE):
    api._conversation = make_conversation(settings, level)
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


def test_graph_and_delete_endpoints(settings):
    c = client(settings)
    sid = c.post("/api/chat", json={"message": "hi"}).json()["session_id"]
    body = c.get(f"/api/sessions/{sid}/graph").json()
    assert body["graph"]["nodes"] == [] and body["coverage"] == 0
    assert c.delete(f"/api/sessions/{sid}").status_code == 204
