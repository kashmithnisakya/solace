from solace.assessment import next_gap
from solace.graph import Domain, GraphStore, GraphUpdate, NodeType
from solace.graph.models import DomainNote, EdgeIn, NodeIn


def node(type_, label, detail="", severity=0):
    return NodeIn(type=type_, label=label, detail=detail, severity=severity)


def test_nodes_merge_by_label_and_keep_highest_severity():
    store = GraphStore(":memory:")
    store.apply("s", GraphUpdate(nodes=[node(NodeType.ISSUE, "Debt", "bank loan", 1)], edges=[], domains=[]))
    g = store.apply("s", GraphUpdate(nodes=[node(NodeType.ISSUE, " debt ", "", 3)], edges=[], domains=[]))
    [n] = g.nodes
    assert (n.mentions, n.severity, n.detail) == (2, 3, "bank loan")


def test_edges_to_unknown_nodes_are_dropped():
    store = GraphStore(":memory:")
    edge = EdgeIn(
        source_type=NodeType.ISSUE,
        source_label="debt",
        target_type=NodeType.EMOTION,
        target_label="fear",
        relation="causes",
    )
    g = store.apply("s", GraphUpdate(nodes=[node(NodeType.ISSUE, "debt")], edges=[edge], domains=[]))
    assert g.edges == []
    g = store.apply("s", GraphUpdate(nodes=[node(NodeType.EMOTION, "fear")], edges=[edge], domains=[]))
    assert len(g.edges) == 1


def test_sessions_are_isolated_and_deletable():
    store = GraphStore(":memory:")
    store.apply("a", GraphUpdate(nodes=[node(NodeType.ISSUE, "grief")], edges=[], domains=[]))
    assert store.load("b").nodes == []
    store.delete("a")
    assert store.load("a").nodes == []


def test_next_gap_waits_then_walks_through_domains():
    store = GraphStore(":memory:")
    assert next_gap(store.load("s")) is None
    g = store.apply("s", GraphUpdate(nodes=[node(NodeType.EMOTION, "sad")], edges=[], domains=[]))
    assert next_gap(g).domain == Domain.ONSET
    g = store.apply(
        "s",
        GraphUpdate(
            nodes=[node(NodeType.SUPPORT, "sister")],
            edges=[],
            domains=[DomainNote(domain=Domain.ONSET, note="two months")],
        ),
    )
    assert next_gap(g).domain == Domain.SLEEP  # support is skipped: they already have a sister
