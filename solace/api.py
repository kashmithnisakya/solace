"""HTTP API and the web app."""

import json
import logging
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from solace import __version__
from solace.assessment import coverage, next_gap
from solace.config import get_settings
from solace.conversation import Conversation, Message, Reply, VoiceTurn
from solace.graph import IssueGraph
from solace.platform.routes import router as platform_router
from solace.safety import Resource, resources_for
from solace.voice import Mint, openai_minter, session_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

FAITHS = {"buddhism", "hinduism", "islam", "christianity"}
WEB = Path(__file__).parent / "web"
SESSION_RE = r"^[a-f0-9]{32}$"

app = FastAPI(title="Solace", version=__version__, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")
_conversation: Conversation | None = None
voice_mint: Mint | None = None  # replaced in tests


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
    "img-src 'self' data:; connect-src 'self' https://api.openai.com; "
    "media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
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
voice_call_limiter = RateLimiter(limit=6, window=60)  # each call costs real money
voice_turn_limiter = RateLimiter(limit=40, window=60)  # spoken turns are short and frequent
handoff_limiter = RateLimiter(limit=5, window=60)
login_limiter = RateLimiter(limit=10, window=300)  # slows down password guessing


def check_rate(request: Request, limiter: RateLimiter | None = None) -> None:
    # Behind a reverse proxy, run uvicorn with --proxy-headers so client.host is the real IP.
    # We never read X-Forwarded-For ourselves: anyone could fake it to dodge the limit.
    client = request.client.host if request.client else "unknown"
    if not (limiter or chat_limiter).allow(client):
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


# ---------- voice ----------


class VoiceStart(BaseModel):
    session_id: str | None = Field(default=None, pattern=SESSION_RE)
    faith: str | None = None

    clean_faith = ChatRequest.clean_faith


class VoiceCall(BaseModel):
    session_id: str
    client_secret: str
    expires_at: int
    model: str
    resources: list[Resource]


@app.post("/api/voice/session")
async def voice_session(req: VoiceStart, request: Request) -> VoiceCall:
    """Start a voice call: a short-lived key for the browser's WebRTC connection to OpenAI."""
    check_rate(request, voice_call_limiter)
    settings = get_settings()
    if not settings.openai_api_key and voice_mint is None:
        raise HTTPException(status_code=503, detail="voice_unavailable")
    session_id = req.session_id or uuid.uuid4().hex
    handoff = conversation().platform.open_for(session_id)
    if handoff and handoff.status == "active":
        raise HTTPException(status_code=409, detail="with_counsellor")
    instructions = await conversation().voice_start(session_id, faith=req.clean_faith())
    try:
        secret = await (voice_mint or openai_minter(settings))(session_config(settings, instructions))
    except Exception as exc:
        logging.getLogger(__name__).exception("could not start a voice session")
        raise HTTPException(status_code=503, detail="voice_unavailable") from exc
    return VoiceCall(
        session_id=session_id,
        client_secret=secret["value"],
        expires_at=secret["expires_at"],
        model=settings.solace_voice_model,
        resources=resources_for(settings.solace_region),
    )


class VoiceText(BaseModel):
    session_id: str = Field(pattern=SESSION_RE)
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=4000)
    faith: str | None = None

    clean_faith = ChatRequest.clean_faith


@app.post("/api/voice/turn", response_model=None)
async def voice_turn(req: VoiceText, request: Request) -> VoiceTurn | Response:
    """A finished transcript from the call. User speech is risk-screened like any typed message."""
    check_rate(request, voice_turn_limiter)
    text = req.text.strip()
    if req.role == "assistant":
        await conversation().voice_assistant(req.session_id, text)
        return Response(status_code=204)
    return await conversation().voice_user(req.session_id, text, faith=req.clean_faith())


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


app.include_router(platform_router)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")
