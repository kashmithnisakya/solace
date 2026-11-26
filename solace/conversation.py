"""Conversation orchestration: safety screen first, then route to the right agent."""

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from agents import Agent, Runner, SQLiteSession
from pydantic import BaseModel

from solace.assistants.classifier import build_classifier
from solace.assistants.companion import build_companion
from solace.assistants.context import UserContext
from solace.assistants.crisis import build_crisis_agent, fallback_crisis_message
from solace.config import Settings
from solace.safety import Resource, RiskAssessment, RiskLevel, combine, keyword_screen, resources_for

log = logging.getLogger(__name__)

Classify = Callable[[list[Any]], Awaitable[RiskAssessment]]
Respond = Callable[[Agent, str, UserContext, SQLiteSession], Awaitable[str]]

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


class Conversation:
    def __init__(
        self,
        settings: Settings,
        classify: Classify | None = None,
        respond: Respond | None = None,
    ) -> None:
        self.settings = settings
        self.companion = build_companion(settings.solace_model)
        self.crisis = build_crisis_agent(settings.solace_model)
        self.classifier = build_classifier(settings.solace_safety_model or settings.solace_model)
        self._classify = classify or self._llm_classify
        self._respond = respond or self._llm_respond
        self._last_level: dict[str, RiskLevel] = {}
        if settings.solace_db_path != ":memory:":
            Path(settings.solace_db_path).parent.mkdir(parents=True, exist_ok=True)

    def session(self, session_id: str) -> SQLiteSession:
        return SQLiteSession(session_id, self.settings.solace_db_path)

    async def send(self, session_id: str, message: str, faith: str | None = None) -> Reply:
        session = self.session(session_id)
        ctx = UserContext(
            faith=faith,
            region=self.settings.solace_region,
            resources=resources_for(self.settings.solace_region),
        )

        risk = await self.assess(session, message)
        previous = self._last_level.get(session_id, RiskLevel.NONE)
        self._last_level[session_id] = risk.level
        # Stay in crisis mode until the risk clearly drops, not just for one message.
        in_crisis = risk.is_crisis or (previous >= RiskLevel.HIGH and risk.level >= RiskLevel.MODERATE)
        agent = self.crisis if in_crisis else self.companion
        if risk.level > RiskLevel.NONE:
            log.info("session=%s risk=%s via %s", session_id, risk.level.name, risk.source)

        try:
            text = await self._respond(agent, message, ctx, session)
        except Exception:
            log.exception("agent failed (session=%s, agent=%s)", session_id, agent.name)
            text = fallback_crisis_message(ctx) if in_crisis else GENERIC_ERROR

        show = in_crisis or risk.show_resources or text == GENERIC_ERROR
        return Reply(
            session_id=session_id,
            reply=text,
            agent=agent.name,
            risk_level=risk.level.name.lower(),
            resources=ctx.resources if show else [],
        )

    async def assess(self, session: SQLiteSession, message: str) -> RiskAssessment:
        quick = keyword_screen(message)
        history = await session.get_items(limit=12)
        try:
            deep = await self._classify([*history, {"role": "user", "content": message}])
        except Exception:
            log.exception("risk classifier failed; using keyword screen only")
            return quick
        return combine(quick, deep)

    async def _llm_classify(self, items: list[Any]) -> RiskAssessment:
        result = await Runner.run(self.classifier, items, max_turns=1)
        out = result.final_output
        return RiskAssessment(level=out.risk_level(), reasons=out.reasons, source="llm")

    @staticmethod
    async def _llm_respond(agent: Agent, message: str, ctx: UserContext, session: SQLiteSession) -> str:
        result = await Runner.run(agent, message, context=ctx, session=session, max_turns=3)
        return str(result.final_output)
