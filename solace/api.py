"""HTTP API and the simple web chat page."""

import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from solace import __version__
from solace.assessment import coverage, next_gap
from solace.config import get_settings
from solace.conversation import Conversation, Reply
from solace.graph import IssueGraph
from solace.safety import Resource, resources_for

logging.basicConfig(level=logging.INFO)

FAITHS = {"buddhism", "hinduism", "islam", "christianity"}
WEB = Path(__file__).parent / "web"

app = FastAPI(title="Solace", version=__version__)
_conversation: Conversation | None = None


def conversation() -> Conversation:
    global _conversation
    if _conversation is None:
        _conversation = Conversation(get_settings())
    return _conversation


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=64)
    faith: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/api/resources")
def resources() -> list[Resource]:
    return resources_for(get_settings().solace_region)


@app.post("/api/chat")
async def chat(req: ChatRequest) -> Reply:
    faith = req.faith.lower() if req.faith and req.faith.lower() in FAITHS else None
    session_id = req.session_id or uuid.uuid4().hex
    return await conversation().send(session_id, req.message.strip(), faith=faith)


SessionId = PathParam(min_length=1, max_length=64)


class GraphView(BaseModel):
    graph: IssueGraph
    coverage: float
    next_area: str | None


@app.get("/api/sessions/{session_id}/graph")
def get_graph(session_id: str = SessionId) -> GraphView:
    graph = conversation().graphs.load(session_id)
    gap = next_gap(graph)
    return GraphView(graph=graph, coverage=coverage(graph), next_area=gap.domain.value if gap else None)


@app.delete("/api/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str = SessionId) -> Response:
    await conversation().delete(session_id)
    return Response(status_code=204)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")
