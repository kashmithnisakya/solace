"""HTTP routes for hand-off to a human counsellor, and the counsellor dashboard API."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from solace.assessment import coverage
from solace.config import get_settings
from solace.graph import IssueGraph
from solace.platform.broker import COUNSELLORS, broker, person
from solace.platform.store import Counsellor, Handoff

router = APIRouter()
SESSION_RE = r"^[a-f0-9]{32}$"
HANDOFF_RE = r"^[a-f0-9]{32}$"
COOKIE = "solace_staff"
SessionId = Annotated[str, PathParam(pattern=SESSION_RE)]
HandoffId = Annotated[str, PathParam(pattern=HANDOFF_RE)]
WEB = Path(__file__).parent.parent / "web"


def _api():
    from solace import api  # late import: api.py includes this router

    return api


def _conv():
    return _api().conversation()


def _store():
    return _conv().platform


async def sse(request: Request, channel: str, who: str | None = None) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        async with broker.subscribe(channel, who) as queue:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except TimeoutError:
                    yield ": keep-alive\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )


# ---------- the person's side (no account; the session id is their key) ----------


class HandoffStatus(BaseModel):
    status: str | None  # None, "requested", "active"
    counsellor: str | None = None
    online: int = 0


class HandoffRequest(BaseModel):
    consent: bool


def _status(session_id: str) -> HandoffStatus:
    h = _store().open_for(session_id)
    online = len(broker.present(COUNSELLORS))
    return HandoffStatus(
        status=h.status if h else None, counsellor=h.counsellor_name if h else None, online=online
    )


@router.get("/api/handoff/availability")
def availability() -> dict[str, int]:
    return {"online": len(broker.present(COUNSELLORS))}


@router.get("/api/sessions/{session_id}/handoff")
def handoff_status(session_id: SessionId) -> HandoffStatus:
    return _status(session_id)


@router.post("/api/sessions/{session_id}/handoff")
def request_handoff(req: HandoffRequest, request: Request, session_id: SessionId) -> HandoffStatus:
    """Ask for a real person. Only with explicit consent: the counsellor will read this conversation."""
    if not req.consent:
        raise HTTPException(status_code=400, detail="consent_required")
    api = _api()
    api.check_rate(request, api.handoff_limiter)
    h = _store().request(session_id, _conv().last_risk(session_id).name.lower())
    broker.publish(COUNSELLORS, {"type": "updated", "handoff_id": h.id})
    return _status(session_id)


@router.delete("/api/sessions/{session_id}/handoff", status_code=204)
def end_handoff(session_id: SessionId) -> Response:
    """The person cancels while waiting, or ends the chat with the counsellor."""
    h = _store().open_for(session_id)
    if h:
        _store().close(h.id, note="Ended by the person.")
        broker.publish(COUNSELLORS, {"type": "updated", "handoff_id": h.id})
        broker.publish(person(session_id), {"type": "handoff", "status": "closed", "by": "person"})
    return Response(status_code=204)


@router.get("/api/sessions/{session_id}/live")
async def person_live(request: Request, session_id: SessionId) -> StreamingResponse:
    return await sse(request, person(session_id))


# ---------- counsellors ----------


def staff(request: Request) -> Counsellor:
    if request.method not in ("GET", "HEAD"):
        # Cookies are SameSite=Strict; also refuse cross-site writes outright.
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            raise HTTPException(status_code=403, detail="bad_origin")
    counsellor = _store().counsellor_for(request.cookies.get(COOKIE))
    if not counsellor:
        raise HTTPException(status_code=401, detail="login_required")
    return counsellor


Staff = Annotated[Counsellor, Depends(staff)]


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


@router.post("/api/counsellor/login")
def login(req: Login, request: Request, response: Response) -> Counsellor:
    api = _api()
    api.check_rate(request, api.login_limiter)
    token = _store().login(req.email, req.password)
    if not token:
        raise HTTPException(status_code=401, detail="wrong_email_or_password")
    response.set_cookie(
        COOKIE,
        token,
        max_age=7 * 86400,
        httponly=True,
        secure=get_settings().solace_secure_cookies,
        samesite="strict",
        path="/",
    )
    return _store().counsellor_for(token)  # type: ignore[return-value]


@router.post("/api/counsellor/logout", status_code=204)
def logout(request: Request, me: Staff) -> Response:
    _store().logout(request.cookies.get(COOKIE, ""))
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path="/")
    return response


@router.get("/api/counsellor/me")
def me(counsellor: Staff) -> Counsellor:
    return counsellor


class QueueItem(BaseModel):
    handoff: Handoff
    preview: str
    mine: bool


@router.get("/api/counsellor/queue")
async def queue(me: Staff) -> list[QueueItem]:
    items = []
    for h in _store().queue(since=time.time() - 86400):
        messages = await _conv().history(h.session_id)
        last = next((m for m in reversed(messages) if m.role == "user"), None)
        items.append(
            QueueItem(handoff=h, preview=(last.text[:140] if last else ""), mine=h.counsellor_id == me.id)
        )
    return items


class HandoffView(BaseModel):
    handoff: Handoff
    messages: list
    graph: IssueGraph
    coverage: float
    resources: list


def _handoff_or_404(handoff_id: str) -> Handoff:
    h = _store().get(handoff_id)
    if not h:
        raise HTTPException(status_code=404, detail="not_found")
    return h


@router.get("/api/counsellor/handoffs/{handoff_id}")
async def view_handoff(handoff_id: HandoffId, me: Staff) -> HandoffView:
    h = _handoff_or_404(handoff_id)
    _store().audit(me.id, "view", h.id)  # every look at a conversation is recorded
    from solace.safety import resources_for

    graph = _conv().graphs.load(h.session_id)
    return HandoffView(
        handoff=h,
        messages=[m.model_dump() for m in await _conv().history(h.session_id)],
        graph=graph,
        coverage=coverage(graph),
        resources=[r.model_dump() for r in resources_for(get_settings().solace_region)],
    )


@router.post("/api/counsellor/handoffs/{handoff_id}/accept")
def accept(handoff_id: HandoffId, me: Staff) -> Handoff:
    h = _store().accept(handoff_id, me.id)
    if not h:
        raise HTTPException(status_code=409, detail="already_taken_or_closed")
    _store().audit(me.id, "accept", h.id)
    broker.publish(COUNSELLORS, {"type": "updated", "handoff_id": h.id})
    broker.publish(person(h.session_id), {"type": "handoff", "status": "active", "name": me.name})
    return h


class CounsellorReply(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


def _mine(handoff_id: str, me: Counsellor) -> Handoff:
    h = _handoff_or_404(handoff_id)
    if h.status != "active" or h.counsellor_id != me.id:
        raise HTTPException(status_code=409, detail="not_your_active_chat")
    return h


@router.post("/api/counsellor/handoffs/{handoff_id}/messages", status_code=204)
async def reply(body: CounsellorReply, handoff_id: HandoffId, me: Staff) -> Response:
    h = _mine(handoff_id, me)
    await _conv().counsellor_message(h.session_id, me.name, body.text.strip())
    _store().audit(me.id, "message", h.id)
    broker.publish(COUNSELLORS, {"type": "updated", "handoff_id": h.id})
    return Response(status_code=204)


class CloseRequest(BaseModel):
    note: str = Field(default="", max_length=2000)


@router.post("/api/counsellor/handoffs/{handoff_id}/close")
def close(body: CloseRequest, handoff_id: HandoffId, me: Staff) -> Handoff:
    h = _handoff_or_404(handoff_id)
    if h.status == "active" and h.counsellor_id != me.id:
        raise HTTPException(status_code=409, detail="not_your_active_chat")
    closed = _store().close(h.id, body.note.strip())
    if not closed:
        raise HTTPException(status_code=409, detail="already_closed")
    _store().audit(me.id, "close", h.id)
    broker.publish(COUNSELLORS, {"type": "updated", "handoff_id": h.id})
    broker.publish(person(h.session_id), {"type": "handoff", "status": "closed", "by": "counsellor"})
    return closed


@router.get("/api/counsellor/live")
async def counsellor_live(request: Request, me: Staff) -> StreamingResponse:
    """Live queue updates. While this is open, the counsellor counts as online."""
    return await sse(request, COUNSELLORS, who=me.id)


@router.get("/counsellor", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(WEB / "counsellor.html")
