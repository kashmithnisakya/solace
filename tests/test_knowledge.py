import pytest
from agents import RunContextWrapper

from solace.assistants.companion import build_companion, companion_instructions
from solace.assistants.context import UserContext
from solace.knowledge import LIBRARY, Passage, load_library, parse_doc, strip_citations
from solace.safety import RiskLevel
from tests.conftest import failing, make_conversation, make_knowledge, word_embed

SID = "b" * 32
FAITHS = {"buddhism", "hinduism", "islam", "christianity"}


def test_library_is_complete_and_sourced():
    chunks = load_library()
    docs = {c.doc for c in chunks}
    assert len(docs) >= 15
    for c in chunks:
        assert c.url.startswith("https://"), c.doc
        assert c.faith in FAITHS | {None}, c.doc
        assert len(c.text) > 80, f"{c.doc}: {c.section} is too thin"
    assert {c.faith for c in chunks if c.faith} == FAITHS


def test_doc_without_front_matter_is_rejected(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("## Just text\nno metadata here")
    with pytest.raises(ValueError):
        parse_doc(bad)


async def test_search_finds_the_right_note():
    found = await make_knowledge().search("I can't sleep at night, my mind keeps racing")
    assert found and found[0].title.startswith("Sleep")
    assert [p.n for p in found] == list(range(1, len(found) + 1))


async def test_faith_notes_only_for_the_chosen_faith():
    kb = make_knowledge(min_score=0.0)
    query = "hardship ease patience prayer Allah"
    assert all("Islam" not in p.title for p in await kb.search(query, faith=None))
    assert all("Islam" not in p.title for p in await kb.search(query, faith="buddhism"))
    assert any("Islam" in p.title for p in await kb.search(query, faith="islam"))


async def test_unrelated_message_gets_no_notes():
    assert await make_knowledge(min_score=0.3).search("quantum chromodynamics lattice gauge") == []


async def test_embeddings_are_cached_between_runs(tmp_path):
    calls: list[int] = []

    async def counting(texts):
        calls.append(len(texts))
        return await word_embed(texts)

    db = str(tmp_path / "kb.db")
    first = make_knowledge(embed=counting)
    first._db.close()
    from solace.knowledge import KnowledgeBase

    await KnowledgeBase(counting, db_path=db).search("sleep")
    await KnowledgeBase(counting, db_path=db).search("sleep")
    library_size = len(load_library(LIBRARY))
    assert calls == [library_size, 1, 1]  # library embedded once, then only the queries


def passage(n, url="https://example.org/a"):
    return Passage(n=n, title=f"Note {n}", section="s", source="WHO", url=url, text="t", score=0.5)


def test_strip_citations_keeps_only_cited_sources_once():
    text, sources = strip_citations(
        "Try slow breathing [1]. It helps [1, 2]. Ignore [9].",
        [passage(1), passage(2, "https://example.org/b"), passage(3, "https://example.org/c")],
    )
    assert text == "Try slow breathing. It helps. Ignore."
    assert [s.n for s in sources] == [1, 2]


def test_companion_prompt_includes_notes_and_citation_rule():
    agent = build_companion(None)
    ctx = UserContext(knowledge=[passage(1)])
    text = companion_instructions(RunContextWrapper(context=ctx), agent)
    assert "[1] Note 1" in text and "marker, like [1]" in text
    ctx.spoken = True
    assert "Don't say marker numbers" in companion_instructions(RunContextWrapper(context=ctx), agent)
    assert "Notes you can draw on" not in companion_instructions(
        RunContextWrapper(context=UserContext()), agent
    )


async def test_reply_cites_and_strips_markers(settings):
    seen = {}

    async def respond(agent, message, ctx, session):
        seen["notes"] = ctx.knowledge
        return "Writing worries down before bed can help [1]."

    conv = make_conversation(settings, respond=respond)
    reply = await conv.send(SID, "I can't sleep, my mind races at night")
    assert seen["notes"]
    assert reply.reply == "Writing worries down before bed can help."
    assert reply.sources and reply.sources[0].url.startswith("https://")


async def test_crisis_replies_get_no_notes(settings):
    seen = {}

    async def respond(agent, message, ctx, session):
        seen["notes"] = ctx.knowledge
        return "I'm here."

    conv = make_conversation(settings, level=RiskLevel.HIGH, respond=respond)
    await conv.send(SID, "I can't sleep and I want to die")
    assert seen["notes"] == []


async def test_search_failure_never_breaks_a_reply(settings):
    conv = make_conversation(settings, knowledge=make_knowledge(embed=failing))
    reply = await conv.send(SID, "I can't sleep")
    assert reply.reply and reply.sources == []


async def test_stream_sends_sources_and_history_hides_markers(settings):
    conv = make_conversation(settings)
    events = [e async for e in conv.stream(SID, "I can't sleep at night, my mind keeps racing")]
    assert events[-1]["type"] == "done" and events[-1]["sources"]
    await conv.voice_assistant(SID, "Slow breathing helps [1].")
    assert (await conv.history(SID))[-1].text == "Slow breathing helps."
