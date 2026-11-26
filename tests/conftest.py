import pytest

from solace.config import Settings
from solace.safety import RiskAssessment, RiskLevel


@pytest.fixture
def settings() -> Settings:
    return Settings(openai_api_key="test", solace_db_path=":memory:", solace_region="LK")


def fixed_classifier(level: RiskLevel):
    async def classify(items):
        return RiskAssessment(level=level, reasons=["test"], source="llm")

    return classify


async def failing(*args, **kwargs):
    raise RuntimeError("model unavailable")


async def echo_agent(agent, message, ctx, session):
    return f"[{agent.name}] {message}"


async def no_graph(summary, message):
    from solace.graph import GraphUpdate

    return GraphUpdate.empty()


def make_conversation(
    settings, level=RiskLevel.NONE, respond=echo_agent, build_graph=no_graph, classify=None
):
    from solace.conversation import Conversation

    return Conversation(
        settings, classify=classify or fixed_classifier(level), respond=respond, build_graph=build_graph
    )
