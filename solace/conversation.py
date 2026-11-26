"""Conversation orchestration: safety screen first, then route to the right agent."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from agents import Agent, Runner, SQLiteSession
from pydantic import BaseModel

from solace.assessment import next_gap
from solace.assistants.classifier import build_classifier
from solace.assistants.companion import build_companion
from solace.assistants.context import UserContext
from solace.assistants.crisis import build_crisis_agent, fallback_crisis_message
from solace.assistants.graph_builder import build_graph_builder, builder_input
from solace.config import Settings
from solace.graph import GraphStore, GraphUpdate, IssueGraph
from solace.safety import Resource, RiskAssessment, RiskLevel, combine, keyword_screen, resources_for

log = logging.getLogger(__name__)

Classify = Callable[[list[Any]], Awaitable[RiskAssessment]]
Respond = Callable[[Agent, str, UserContext, SQLiteSession], Awaitable[str]]
BuildGraph = Callable[[str, str], Awaitable[GraphUpdate]]

GENERIC_ERROR = (
    "I'm sorry, I'm having trouble responding right now. Please try again in a moment. "
    "If you need to talk to someone urgently, the support lines below are free and confidential."
)


class Reply(BaseModel):
    session_id: str
    reply: str
    agent: str
    risk_level: str
    resources: list[Resource]
    graph: IssueGraph


class Conversation:
    def __init__(
        self,
        settings: Settings,
        classify: Classify | None = None,
        respond: Respond | None = None,
        build_graph: BuildGraph | None = None,
    ) -> None:
        self.settings = settings
        self.companion = build_companion(settings.solace_model)
        self.crisis = build_crisis_agent(settings.solace_model)
        helper_model = settings.solace_safety_model or settings.solace_model
        self.classifier = build_classifier(helper_model)
        self.graph_builder = build_graph_builder(helper_model)
        self._classify = classify or self._llm_classify
        self._respond = respond or self._llm_respond
        self._build_graph = build_graph or self._llm_build_graph
        self._last_level: dict[str, RiskLevel] = {}
        if settings.solace_db_path != ":memory:":
            Path(settings.solace_db_path).parent.mkdir(parents=True, exist_ok=True)
        self.graphs = GraphStore(settings.solace_db_path)

    def session(self, session_id: str) -> SQLiteSession:
        return SQLiteSession(session_id, self.settings.solace_db_path)

    async def send(self, session_id: str, message: str, faith: str | None = None) -> Reply:
        session = self.session(session_id)
        graph = self.graphs.load(session_id)

        risk = await self.assess(session, message)
        previous = self._last_level.get(session_id, RiskLevel.NONE)
        self._last_level[session_id] = risk.level
        # Stay in crisis mode until the risk clearly drops, not just for one message.
        in_crisis = risk.is_crisis or (previous >= RiskLevel.HIGH and risk.level >= RiskLevel.MODERATE)
        agent = self.crisis if in_crisis else self.companion
        if risk.level > RiskLevel.NONE:
            log.info("session=%s risk=%s via %s", session_id, risk.level.name, risk.source)

        gap = None if in_crisis else next_gap(graph)
        ctx = UserContext(
            faith=faith,
            region=self.settings.solace_region,
            resources=resources_for(self.settings.solace_region),
            graph_summary=graph.summary(),
            next_gap=gap.hint if gap else None,
        )

        # The reply and the graph update run at the same time, so mapping adds no delay.
        text, update = await asyncio.gather(
            self._safe_respond(agent, message, ctx, session, in_crisis),
            self._safe_build_graph(graph.summary(), message),
        )
        if update.nodes or update.edges or update.domains:
            graph = self.graphs.apply(session_id, update)

        show = in_crisis or risk.show_resources or text == GENERIC_ERROR
        return Reply(
            session_id=session_id,
            reply=text,
            agent=agent.name,
            risk_level=risk.level.name.lower(),
            resources=ctx.resources if show else [],
            graph=graph,
        )

    async def delete(self, session_id: str) -> None:
        """Forget everything about a conversation: messages, graph and risk state."""
        await self.session(session_id).clear_session()
        self.graphs.delete(session_id)
        self._last_level.pop(session_id, None)

    async def assess(self, session: SQLiteSession, message: str) -> RiskAssessment:
        quick = keyword_screen(message)
        history = await session.get_items(limit=12)
        try:
            deep = await self._classify([*history, {"role": "user", "content": message}])
        except Exception:
            log.exception("risk classifier failed; using keyword screen only")
            return quick
        return combine(quick, deep)

    async def _safe_respond(
        self, agent: Agent, message: str, ctx: UserContext, session: SQLiteSession, in_crisis: bool
    ) -> str:
        try:
            return await self._respond(agent, message, ctx, session)
        except Exception:
            log.exception("agent failed (agent=%s)", agent.name)
            return fallback_crisis_message(ctx) if in_crisis else GENERIC_ERROR

    async def _safe_build_graph(self, summary: str, message: str) -> GraphUpdate:
        try:
            return await self._build_graph(summary, message)
        except Exception:
            log.exception("graph builder failed; graph left unchanged")
            return GraphUpdate.empty()

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
