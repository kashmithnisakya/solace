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
