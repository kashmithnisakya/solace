"""Conversation orchestration: safety screen first, then route to the right agent.

Each message is a "turn":
1. prepare: load the graph, screen for risk, choose the agent, build its context
2. reply:   the agent answers (all at once, or streamed word by word) while the
            graph builder runs in parallel
3. finish:  save the graph update
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents import Agent, RunContextWrapper, Runner, SQLiteSession
from openai.types.responses import ResponseTextDeltaEvent
from pydantic import BaseModel

from solace.assessment import next_gap
from solace.assistants.classifier import build_classifier
from solace.assistants.companion import build_companion
from solace.assistants.context import UserContext
from solace.assistants.crisis import build_crisis_agent, fallback_crisis_message
from solace.assistants.graph_builder import build_graph_builder, builder_input
from solace.config import Settings
from solace.graph import GraphStore, GraphUpdate, IssueGraph
from solace.knowledge import KnowledgeBase, Passage, Source, clean_markers, openai_embedder, strip_citations
from solace.safety import Resource, RiskAssessment, RiskLevel, combine, keyword_screen, resources_for
from solace.voice import voice_instructions

log = logging.getLogger(__name__)

Classify = Callable[[list[Any]], Awaitable[RiskAssessment]]
Respond = Callable[[Agent, str, UserContext, SQLiteSession], Awaitable[str]]
StreamRespond = Callable[[Agent, str, UserContext, SQLiteSession], AsyncIterator[str]]
BuildGraph = Callable[[str, str], Awaitable[GraphUpdate]]

GENERIC_ERROR = (
    "I'm sorry, I'm having trouble responding right now. Please try again in a moment. "
    "If you need to talk to someone urgently, the support lines below are free and confidential."
)


class TurnInfo(BaseModel):
    """What the client needs to know before the reply text arrives."""

    session_id: str
    agent: str
    risk_level: str
    resources: list[Resource]


class Reply(TurnInfo):
    reply: str
    graph: IssueGraph
    sources: list[Source] = []  # knowledge base sources the reply actually cited


class Message(BaseModel):
    role: str  # "user" or "assistant"
    text: str


class VoiceTurn(TurnInfo):
    """What the browser needs after a spoken message: risk, and the instructions to use from now on."""

    in_crisis: bool
    instructions: str


@dataclass
class _Turn:
    session_id: str
    message: str
    session: SQLiteSession
    agent: Agent
    ctx: UserContext
    risk: RiskAssessment
    in_crisis: bool
    graph: IssueGraph

    def info(self) -> TurnInfo:
        return TurnInfo(
            session_id=self.session_id,
            agent=self.agent.name,
            risk_level=self.risk.level.name.lower(),
            resources=self.ctx.resources if (self.in_crisis or self.risk.show_resources) else [],
        )


class Conversation:
    def __init__(
        self,
        settings: Settings,
        classify: Classify | None = None,
        respond: Respond | None = None,
        build_graph: BuildGraph | None = None,
        stream_respond: StreamRespond | None = None,
        knowledge: KnowledgeBase | None = None,
    ) -> None:
        self.settings = settings
        self.knowledge = knowledge or KnowledgeBase(
            openai_embedder(settings.openai_api_key, settings.solace_embedding_model),
            db_path=settings.solace_db_path,
            model=settings.solace_embedding_model,
            min_score=settings.solace_knowledge_min_score,
        )
        self.companion = build_companion(settings.solace_model)
        self.crisis = build_crisis_agent(settings.solace_model)
        helper_model = settings.solace_safety_model or settings.solace_model
        self.classifier = build_classifier(helper_model)
        self.graph_builder = build_graph_builder(helper_model)
        self._classify = classify or self._llm_classify
        self._respond = respond or self._llm_respond
        self._build_graph = build_graph or self._llm_build_graph
        if stream_respond:
            self._stream = stream_respond
        elif respond:
            self._stream = self._single_chunk  # tests that only fake `respond` still work when streaming
        else:
            self._stream = self._llm_stream
        self._last_level: dict[str, RiskLevel] = {}
        self._memory_sessions: dict[str, SQLiteSession] = {}
        self._background: set[asyncio.Task] = set()
        if settings.solace_db_path != ":memory:":
            Path(settings.solace_db_path).parent.mkdir(parents=True, exist_ok=True)
        self.graphs = GraphStore(settings.solace_db_path)

    def session(self, session_id: str) -> SQLiteSession:
        if self.settings.solace_db_path == ":memory:":
            # Each in-memory SQLiteSession is its own database, so keep one per conversation.
            if session_id not in self._memory_sessions:
                self._memory_sessions[session_id] = SQLiteSession(session_id)
            return self._memory_sessions[session_id]
        return SQLiteSession(session_id, self.settings.solace_db_path)

    # ---------- public API ----------

    async def send(self, session_id: str, message: str, faith: str | None = None) -> Reply:
        turn = await self._prepare(session_id, message, faith)
        text, update = await asyncio.gather(self._safe_respond(turn), self._safe_build_graph(turn))
        graph = self._finish(turn, update)
        info = turn.info()
        if text == GENERIC_ERROR:
            info.resources = turn.ctx.resources  # always offer real help when we can't
        text, sources = strip_citations(text, turn.ctx.knowledge)
        return Reply(**info.model_dump(), reply=text, graph=graph, sources=sources)

    async def stream(self, session_id: str, message: str, faith: str | None = None) -> AsyncIterator[dict]:
        """Yield events: {"type": "start", ...}, {"type": "delta", "text"}, {"type": "done", "graph"}."""
        turn = await self._prepare(session_id, message, faith)
        yield {"type": "start", **turn.info().model_dump(mode="json")}

        graph_task = asyncio.create_task(self._safe_build_graph(turn))
        sent_any = False
        try:
            async for chunk in self._stream(turn.agent, turn.message, turn.ctx, turn.session):
                sent_any = True
                yield {"type": "delta", "text": chunk}
        except Exception:
            log.exception("streaming failed (agent=%s)", turn.agent.name)
            fallback = fallback_crisis_message(turn.ctx) if turn.in_crisis else GENERIC_ERROR
            prefix = "\n\n" if sent_any else ""
            yield {"type": "delta", "text": prefix + fallback}
            if not turn.in_crisis:
                yield {"type": "resources", "resources": [r.model_dump() for r in turn.ctx.resources]}

        graph = self._finish(turn, await graph_task)
        # The client strips [n] markers and shows only the sources the reply cited.
        sources = [_source(p).model_dump() for p in turn.ctx.knowledge]
        yield {"type": "done", "graph": graph.model_dump(mode="json"), "sources": sources}

    async def history(self, session_id: str) -> list[Message]:
        """The visible messages of a conversation, for restoring the chat after a reload."""
        out: list[Message] = []
        for item in await self.session(session_id).get_items():
            text = _item_text(item)
            if text and item.get("role") in ("user", "assistant"):
                if item["role"] == "assistant":
                    text = clean_markers(text)
                out.append(Message(role=item["role"], text=text))
        return out

    async def delete(self, session_id: str) -> None:
        """Forget everything about a conversation: messages, graph and risk state."""
        await self.session(session_id).clear_session()
        self.graphs.delete(session_id)
        self._last_level.pop(session_id, None)

    # ---------- voice ----------

    async def voice_start(self, session_id: str, faith: str | None = None) -> str:
        """Instructions for a new voice call, carrying on from wherever the conversation is."""
        graph = self.graphs.load(session_id)
        in_crisis = self._last_level.get(session_id, RiskLevel.NONE) >= RiskLevel.HIGH
        agent = self.crisis if in_crisis else self.companion
        return await self._spoken(agent, self._context(graph, in_crisis, faith), session_id, opening=True)

    async def voice_user(self, session_id: str, text: str, faith: str | None = None) -> VoiceTurn:
        """A finished user transcript: screen it, save it, and return the instructions to use next."""
        turn = await self._prepare(session_id, text, faith)
        turn.ctx.spoken = True
        await turn.session.add_items([{"role": "user", "content": text}])
        task = asyncio.create_task(self._update_graph(turn))  # don't make a spoken reply wait for this
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        instructions = await self._spoken(turn.agent, turn.ctx, session_id)
        return VoiceTurn(**turn.info().model_dump(), in_crisis=turn.in_crisis, instructions=instructions)

    async def voice_assistant(self, session_id: str, text: str) -> None:
        """What Solace said out loud, so the chat and later replies remember it."""
        await self.session(session_id).add_items([{"role": "assistant", "content": text}])

    async def _update_graph(self, turn: _Turn) -> None:
        self._finish(turn, await self._safe_build_graph(turn))

    async def _spoken(self, agent: Agent, ctx: UserContext, session_id: str, opening: bool = False) -> str:
        base = await agent.get_system_prompt(RunContextWrapper(context=ctx))
        recent = (await self.history(session_id))[-10:]
        if recent:
            lines = "\n".join(f"{m.role}: {m.text[:400]}" for m in recent)
            base += f"\n# The conversation so far (continue it naturally, don't repeat yourself)\n{lines}\n"
        return voice_instructions(base or "", opening)

    async def assess(self, session: SQLiteSession, message: str) -> RiskAssessment:
        quick = keyword_screen(message)
        history = await session.get_items(limit=12)
        try:
            deep = await self._classify([*history, {"role": "user", "content": message}])
        except Exception:
            log.exception("risk classifier failed; using keyword screen only")
            return quick
        return combine(quick, deep)

    # ---------- turn steps ----------

    async def _prepare(self, session_id: str, message: str, faith: str | None) -> _Turn:
        session = self.session(session_id)
        graph = self.graphs.load(session_id)

        # Look up notes while the risk check runs, so it adds no waiting.
        risk, notes = await asyncio.gather(self.assess(session, message), self._search(message, faith))
        previous = self._last_level.get(session_id, RiskLevel.NONE)
        self._last_level[session_id] = risk.level
        # Stay in crisis mode until the risk clearly drops, not just for one message.
        in_crisis = risk.is_crisis or (previous >= RiskLevel.HIGH and risk.level >= RiskLevel.MODERATE)
        agent = self.crisis if in_crisis else self.companion
        if risk.level > RiskLevel.NONE:
            log.info("risk=%s via %s", risk.level.name, risk.source)  # never log message content

        ctx = self._context(graph, in_crisis, faith)
        ctx.knowledge = [] if in_crisis else notes  # crisis replies stay focused on safety
        return _Turn(session_id, message, session, agent, ctx, risk, in_crisis, graph)

    def _context(self, graph: IssueGraph, in_crisis: bool, faith: str | None) -> UserContext:
        gap = None if in_crisis else next_gap(graph)
        return UserContext(
            faith=faith,
            region=self.settings.solace_region,
            resources=resources_for(self.settings.solace_region),
            graph_summary=graph.summary(),
            next_gap=gap.hint if gap else None,
        )

    async def _search(self, message: str, faith: str | None) -> list[Passage]:
        try:
            return await self.knowledge.search(message, faith=faith)
        except Exception:
            log.exception("knowledge search failed; replying without notes")
            return []

    def _finish(self, turn: _Turn, update: GraphUpdate) -> IssueGraph:
        if update.nodes or update.edges or update.domains:
            return self.graphs.apply(turn.session_id, update)
        return turn.graph

    async def _safe_respond(self, turn: _Turn) -> str:
        try:
            return await self._respond(turn.agent, turn.message, turn.ctx, turn.session)
        except Exception:
            log.exception("agent failed (agent=%s)", turn.agent.name)
            return fallback_crisis_message(turn.ctx) if turn.in_crisis else GENERIC_ERROR

    async def _safe_build_graph(self, turn: _Turn) -> GraphUpdate:
        try:
            return await self._build_graph(turn.graph.summary(), turn.message)
        except Exception:
            log.exception("graph builder failed; graph left unchanged")
            return GraphUpdate.empty()

    # ---------- LLM calls (replaced by fakes in tests) ----------

    async def _llm_classify(self, items: list[Any]) -> RiskAssessment:
        result = await Runner.run(self.classifier, items, max_turns=1)
        out = result.final_output
        return RiskAssessment(level=out.risk_level(), reasons=out.reasons, source="llm")

    async def _llm_build_graph(self, summary: str, message: str) -> GraphUpdate:
        result = await Runner.run(self.graph_builder, builder_input(summary, message), max_turns=1)
        return result.final_output

    @staticmethod
    async def _llm_respond(agent: Agent, message: str, ctx: UserContext, session: SQLiteSession) -> str:
        result = await Runner.run(agent, message, context=ctx, session=session, max_turns=3)
        return str(result.final_output)

    @staticmethod
    async def _llm_stream(
        agent: Agent, message: str, ctx: UserContext, session: SQLiteSession
    ) -> AsyncIterator[str]:
        result = Runner.run_streamed(agent, message, context=ctx, session=session, max_turns=3)
        async for event in result.stream_events():
            if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                yield event.data.delta

    async def _single_chunk(
        self, agent: Agent, message: str, ctx: UserContext, session: SQLiteSession
    ) -> AsyncIterator[str]:
        yield await self._respond(agent, message, ctx, session)


def _source(p: Passage) -> Source:
    return Source(n=p.n, title=p.title, source=p.source, url=p.url)


def _item_text(item: Any) -> str:
    content = item.get("content") if isinstance(item, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""
