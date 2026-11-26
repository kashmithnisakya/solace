from solace.conversation import GENERIC_ERROR
from solace.graph import GraphUpdate, NodeType
from solace.graph.models import DomainNote, EdgeIn, NodeIn
from solace.safety import RiskAssessment, RiskLevel
from tests.conftest import failing, make_conversation


async def test_ordinary_message_goes_to_companion(settings):
    reply = await make_conversation(settings, RiskLevel.LOW).send("s1", "I've been feeling lonely")
    assert reply.agent == "Companion"
    assert reply.resources == []


async def test_high_risk_goes_to_crisis_with_resources(settings):
    reply = await make_conversation(settings, RiskLevel.HIGH).send("s1", "I can't do this anymore")
    assert reply.agent == "Crisis Support"
    assert any(r.contact == "1926" for r in reply.resources)


async def test_keywords_override_a_low_llm_rating(settings):
    reply = await make_conversation(settings, RiskLevel.NONE).send("s1", "I want to kill myself")
    assert reply.agent == "Crisis Support"


async def test_classifier_failure_falls_back_to_keywords(settings):
    reply = await make_conversation(settings, classify=failing).send("s1", "I want to die")
    assert reply.agent == "Crisis Support"


async def test_crisis_never_returns_an_error(settings):
    reply = await make_conversation(settings, RiskLevel.IMMINENT, respond=failing).send("s1", "goodbye")
    assert "1926" in reply.reply
    assert reply.resources


async def test_non_crisis_failure_shows_resources(settings):
    reply = await make_conversation(settings, respond=failing).send("s1", "hello")
    assert reply.reply == GENERIC_ERROR
    assert reply.resources


async def test_crisis_mode_is_sticky_until_risk_drops(settings):
    levels = iter([RiskLevel.HIGH, RiskLevel.MODERATE, RiskLevel.LOW])

    async def classify(items):
        return RiskAssessment(level=next(levels), source="llm")

    conv = make_conversation(settings, classify=classify)
    assert (await conv.send("s1", "a")).agent == "Crisis Support"
    assert (await conv.send("s1", "b")).agent == "Crisis Support"
    assert (await conv.send("s1", "c")).agent == "Companion"


EXAMS = GraphUpdate(
    nodes=[
        NodeIn(type=NodeType.ISSUE, label="exam stress", detail="A/L exams next month", severity=2),
        NodeIn(type=NodeType.ISSUE, label="poor sleep", detail="", severity=2),
    ],
    edges=[
        EdgeIn(
            source_type=NodeType.ISSUE,
            source_label="exam stress",
            target_type=NodeType.ISSUE,
            target_label="poor sleep",
            relation="causes",
        ),
    ],
    domains=[DomainNote(domain="sleep", note="sleeps 3-4 hours")],
)


async def test_graph_is_built_and_guides_the_next_question(settings):
    seen = {}

    async def build(summary, message):
        return EXAMS

    async def respond(agent, message, ctx, session):
        seen["gap"], seen["summary"] = ctx.next_gap, ctx.graph_summary
        return "ok"

    conv = make_conversation(settings, respond=respond, build_graph=build)
    reply = await conv.send("s1", "exams are stressing me out and I can't sleep")
    assert {n.label for n in reply.graph.nodes} == {"exam stress", "poor sleep"}
    assert seen["gap"] is None  # nothing known before the first message, so just listen

    await conv.send("s1", "yeah")
    assert "exam stress causes poor sleep" in seen["summary"]
    assert "when this started" in seen["gap"]


async def test_crisis_agent_gets_no_assessment_questions(settings):
    seen = {}

    async def respond(agent, message, ctx, session):
        seen["gap"] = ctx.next_gap
        return "ok"

    async def build(summary, message):
        return EXAMS

    conv = make_conversation(settings, RiskLevel.HIGH, respond=respond, build_graph=build)
    await conv.send("s1", "first")
    await conv.send("s1", "second")
    assert seen["gap"] is None


async def test_graph_builder_failure_does_not_break_the_reply(settings):
    reply = await make_conversation(settings, build_graph=failing).send("s1", "hello")
    assert reply.reply == "[Companion] hello"
    assert reply.graph.nodes == []


async def test_delete_forgets_everything(settings):
    async def build(summary, message):
        return EXAMS

    conv = make_conversation(settings, RiskLevel.HIGH, build_graph=build)
    await conv.send("s1", "hi")
    await conv.delete("s1")
    assert conv.graphs.load("s1").nodes == []
    assert await conv.session("s1").get_items() == []
    assert "s1" not in conv._last_level


async def collect(gen):
    return [e async for e in gen]


async def test_stream_yields_chunks_in_order(settings):
    async def stream(agent, message, ctx, session):
        for word in ["Hey ", "there."]:
            yield word

    conv = make_conversation(settings)
    conv._stream = stream
    evs = await collect(conv.stream("s1", "hi"))
    assert "".join(e["text"] for e in evs if e["type"] == "delta") == "Hey there."
    assert evs[-1]["type"] == "done"


async def test_stream_failure_in_crisis_sends_safety_message(settings):
    async def broken(agent, message, ctx, session):
        yield "I'm "
        raise RuntimeError("connection dropped")

    conv = make_conversation(settings, RiskLevel.IMMINENT)
    conv._stream = broken
    text = "".join(e.get("text", "") for e in await collect(conv.stream("s1", "x")))
    assert text.startswith("I'm ") and "1926" in text


async def test_stream_failure_outside_crisis_offers_resources(settings):
    conv = make_conversation(settings, respond=failing)
    evs = await collect(conv.stream("s1", "hello"))
    assert any(e["type"] == "resources" for e in evs)
