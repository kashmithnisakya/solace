"""SQLite storage for issue graphs, one graph per conversation."""

import sqlite3
import threading
from pathlib import Path

from solace.graph.models import Domain, Edge, GraphUpdate, IssueGraph, Node, NodeType, node_id

SCHEMA = """
CREATE TABLE IF NOT EXISTS graph_nodes (
    session_id TEXT NOT NULL, id TEXT NOT NULL, type TEXT NOT NULL, label TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '', severity INTEGER NOT NULL DEFAULT 0, mentions INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (session_id, id)
);
CREATE TABLE IF NOT EXISTS graph_edges (
    session_id TEXT NOT NULL, source TEXT NOT NULL, target TEXT NOT NULL, relation TEXT NOT NULL,
    weight INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (session_id, source, target, relation)
);
CREATE TABLE IF NOT EXISTS graph_domains (
    session_id TEXT NOT NULL, domain TEXT NOT NULL, note TEXT NOT NULL,
    PRIMARY KEY (session_id, domain)
);
"""


class GraphStore:
    def __init__(self, db_path: str) -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    def load(self, session_id: str) -> IssueGraph:
        with self._lock:
            nodes = self._db.execute(
                "SELECT id, type, label, detail, severity, mentions FROM graph_nodes WHERE session_id=?",
                (session_id,),
            ).fetchall()
            edges = self._db.execute(
                "SELECT source, target, relation, weight FROM graph_edges WHERE session_id=?", (session_id,)
            ).fetchall()
            domains = self._db.execute(
                "SELECT domain, note FROM graph_domains WHERE session_id=?", (session_id,)
            ).fetchall()
        return IssueGraph(
            nodes=[
                Node(id=i, type=t, label=lb, detail=d, severity=s, mentions=m) for i, t, lb, d, s, m in nodes
            ],
            edges=[Edge(source=s, target=t, relation=r, weight=w) for s, t, r, w in edges],
            domains={Domain(d): note for d, note in domains},
        )

    def apply(self, session_id: str, update: GraphUpdate) -> IssueGraph:
        with self._lock, self._db:
            for n in update.nodes:
                if not n.label.strip():
                    continue
                self._db.execute(
                    """INSERT INTO graph_nodes (session_id, id, type, label, detail, severity)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT (session_id, id) DO UPDATE SET
                         mentions = mentions + 1,
                         detail = CASE WHEN excluded.detail != '' THEN excluded.detail ELSE detail END,
                         severity = MAX(severity, excluded.severity)""",
                    (
                        session_id,
                        node_id(n.type, n.label),
                        n.type.value,
                        n.label.strip(),
                        n.detail.strip(),
                        n.severity if n.type == NodeType.ISSUE else 0,
                    ),
                )
            for e in update.edges:
                src, dst = node_id(e.source_type, e.source_label), node_id(e.target_type, e.target_label)
                exists = self._db.execute(
                    "SELECT COUNT(*) FROM graph_nodes WHERE session_id=? AND id IN (?, ?)",
                    (session_id, src, dst),
                ).fetchone()[0]
                if src == dst or exists < 2:
                    continue  # never store an edge to a node we don't have
                self._db.execute(
                    """INSERT INTO graph_edges (session_id, source, target, relation) VALUES (?, ?, ?, ?)
                       ON CONFLICT DO UPDATE SET weight = weight + 1""",
                    (session_id, src, dst, e.relation.value),
                )
            for d in update.domains:
                if d.note.strip():
                    self._db.execute(
                        """INSERT INTO graph_domains (session_id, domain, note) VALUES (?, ?, ?)
                           ON CONFLICT DO UPDATE SET note = excluded.note""",
                        (session_id, d.domain.value, d.note.strip()),
                    )
        return self.load(session_id)

    def delete(self, session_id: str) -> None:
        with self._lock, self._db:
            for table in ("graph_nodes", "graph_edges", "graph_domains"):
                self._db.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
