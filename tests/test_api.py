import json

from fastapi.testclient import TestClient

from solace import api
from solace.safety import RiskLevel
from tests.conftest import make_conversation


def client(settings, level=RiskLevel.NONE):
    api._conversation = make_conversation(settings, level)
    api.chat_limiter.hits.clear()
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


def events(res):
    return [json.loads(line[5:]) for line in res.text.split("\n\n") if line.startswith("data:")]


def test_stream_sends_start_delta_done(settings):
    res = client(settings).post("/api/chat/stream", json={"message": "hello"})
    assert res.headers["content-type"].startswith("text/event-stream")
    evs = events(res)
    assert [e["type"] for e in evs] == ["start", "delta", "done"]
    assert evs[0]["agent"] == "Companion" and evs[1]["text"] == "[Companion] hello"


def test_stream_crisis_includes_resources(settings):
    evs = events(client(settings, RiskLevel.HIGH).post("/api/chat/stream", json={"message": "x"}))
    assert evs[0]["agent"] == "Crisis Support"
    assert any(r["contact"] == "1926" for r in evs[0]["resources"])


def test_messages_restore_after_reload(settings):
    c = client(settings)
    sid = c.post("/api/chat", json={"message": "hi"}).json()["session_id"]
    assert c.get(f"/api/sessions/{sid}/messages").status_code == 200


def test_rejects_made_up_session_ids(settings):
    c = client(settings)
    assert c.post("/api/chat", json={"message": "hi", "session_id": "../../etc"}).status_code == 422
    assert c.get("/api/sessions/abc/graph").status_code == 422


def test_rate_limit_still_offers_help(settings):
    c = client(settings)
    api.chat_limiter.limit = 2
    try:
        codes = [c.post("/api/chat", json={"message": "hi"}).status_code for _ in range(3)]
        res = c.post("/api/chat", json={"message": "hi"})
    finally:
        api.chat_limiter.limit = 20
    assert codes == [200, 200, 429]
    assert any(r["contact"] == "1926" for r in res.json()["resources"])


def test_security_headers(settings):
    res = client(settings).get("/")
    assert "frame-ancestors 'none'" in res.headers["content-security-policy"]
    assert res.headers["x-content-type-options"] == "nosniff"
    assert client(settings).get("/static/app.js").status_code == 200
