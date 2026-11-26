"""HTTP API and the simple web chat page."""

import logging
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from solace import __version__
from solace.config import get_settings
from solace.conversation import Conversation, Reply
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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")
