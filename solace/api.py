"""HTTP API and the web app."""

import json
import logging
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from solace import __version__
from solace.assessment import coverage, next_gap
from solace.config import get_settings
from solace.conversation import Conversation, Message, Reply
from solace.graph import IssueGraph
from solace.safety import Resource, resources_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

FAITHS = {"buddhism", "hinduism", "islam", "christianity"}
WEB = Path(__file__).parent / "web"
SESSION_RE = r"^[a-f0-9]{32}$"

app = FastAPI(title="Solace", version=__version__, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")
_conversation: Conversation | None = None


def conversation() -> Conversation:
    global _conversation
    if _conversation is None:
        _conversation = Conversation(get_settings())
    return _conversation


# ---------- security headers ----------

CSP = (
    "default-src 'self'; script-src 'self' https://cdnjs.cloudflare.com; "
    # The hash allows only the small stylesheet Cytoscape 3.30.2 injects; update it if the version changes.
    "style-src 'self' 'sha256-pgvDUBa4IjFA2yuSJ2cqcyxmNYJMborsd0ORcRv9vw8='; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"  # conversations are private
    return response


# ---------- rate limiting ----------


class RateLimiter:
    """Simple in-memory sliding window per client. Use a shared store (e.g. Redis) when scaling out."""

    def __init__(self, limit: int, window: float) -> None:
        self.limit, self.window = limit, window
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


chat_limiter = RateLimiter(limit=20, window=60)


def check_rate(request: Request) -> None:
    # Behind a reverse proxy, run uvicorn with --proxy-headers so client.host is the real IP.
    # We never read X-Forwarded-For ourselves: anyone could fake it to dodge the limit.
    client = request.client.host if request.client else "unknown"
    if not chat_limiter.allow(client):
        raise HTTPException(status_code=429, detail="slow_down")


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    body: dict = {"detail": exc.detail}
    if exc.status_code == 429:
        # Someone hitting a limit may still be in crisis: always include real help.
        body["message"] = "You're sending messages quickly. Take a breath, and try again in a minute."
        body["resources"] = [r.model_dump() for r in resources_for(get_settings().solace_region)]
    return JSONResponse(body, status_code=exc.status_code, headers=getattr(exc, "headers", None))


# ---------- API ----------


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, pattern=SESSION_RE)
    faith: str | None = None

    def clean_faith(self) -> str | None:
        return self.faith.lower() if self.faith and self.faith.lower() in FAITHS else None


SessionId = PathParam(pattern=SESSION_RE)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/api/resources")
def resources() -> list[Resource]:
    return resources_for(get_settings().solace_region)


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request) -> Reply:
    check_rate(request)
    session_id = req.session_id or uuid.uuid4().hex
    return await conversation().send(session_id, req.message.strip(), faith=req.clean_faith())


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    """Server-sent events: start → delta… → done. Lets the reply appear as it is written."""
    check_rate(request)
    session_id = req.session_id or uuid.uuid4().hex

    async def events() -> AsyncIterator[str]:
        async for event in conversation().stream(session_id, req.message.strip(), faith=req.clean_faith()):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )


@app.get("/api/sessions/{session_id}/messages")
async def get_messages(session_id: str = SessionId) -> list[Message]:
    return await conversation().history(session_id)


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
