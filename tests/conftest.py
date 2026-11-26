import hashlib
import re

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


async def word_embed(texts):
    """Offline stand-in for embeddings: a hashed bag of word stems, so similar words match."""
    out = []
    for text in texts:
        vec = [0.0] * 256
        for word in re.findall(r"[a-z]+", text.lower()):
            if len(word) > 3:
                vec[int(hashlib.md5(word[:5].encode()).hexdigest(), 16) % 256] += 1.0
        out.append(vec)
    return out


def make_knowledge(min_score=0.2, embed=word_embed, chunks=None):
    from solace.knowledge import KnowledgeBase

    return KnowledgeBase(embed, chunks=chunks, min_score=min_score)


def make_conversation(
    settings, level=RiskLevel.NONE, respond=echo_agent, build_graph=no_graph, classify=None, knowledge=None
):
    from solace.conversation import Conversation

    return Conversation(
        settings,
        classify=classify or fixed_classifier(level),
        respond=respond,
        build_graph=build_graph,
        knowledge=knowledge or make_knowledge(),
    )
