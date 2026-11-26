"""Data models for the issue graph."""

import re
from enum import StrEnum

from pydantic import BaseModel, Field


class NodeType(StrEnum):
    ISSUE = "issue"  # a problem: debt, exams, a breakup, poor sleep
    EMOTION = "emotion"  # sadness, anger, guilt, fear
    TRIGGER = "trigger"  # something that sets it off: nights alone, arguments
    PERSON = "person"  # someone involved: mother, partner, boss
    SUPPORT = "support"  # something or someone that helps: a friend, prayer, walking
    STRENGTH = "strength"  # a personal strength: caring, determined, honest


class Relation(StrEnum):
    CAUSES = "causes"
    WORSENS = "worsens"
    RELATED_TO = "related_to"
    HELPS_WITH = "helps_with"


class Domain(StrEnum):
    """Areas worth gently understanding, loosely inspired by PHQ-9 and GAD-7. Not a diagnosis."""

    ONSET = "onset"  # when it started, how long it has lasted
    MOOD = "mood"
    INTEREST = "interest"  # enjoyment of things they used to like
    SLEEP = "sleep"
    APPETITE = "appetite"
    ENERGY = "energy"
    CONCENTRATION = "concentration"
    SELF_WORTH = "self_worth"
    ANXIETY = "anxiety"
    SUPPORT = "support"  # who they can turn to
    FUNCTIONING = "functioning"  # work, study, family life, daily tasks


def node_id(type_: NodeType | str, label: str) -> str:
    return f"{NodeType(type_).value}:{re.sub(r'\s+', ' ', label.strip().lower())}"


class Node(BaseModel):
    id: str
    type: NodeType
    label: str
    detail: str = ""
    severity: int = Field(default=0, ge=0, le=3)  # 0 unknown, 1 mild, 2 moderate, 3 severe
    mentions: int = 1


class Edge(BaseModel):
    source: str
    target: str
    relation: Relation
    weight: int = 1


class IssueGraph(BaseModel):
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    domains: dict[Domain, str] = Field(default_factory=dict)

    def of_type(self, type_: NodeType) -> list[Node]:
        return [n for n in self.nodes if n.type == type_]

    def summary(self) -> str:
        """A compact text version for agent prompts."""
        if not self.nodes and not self.domains:
            return "Nothing known yet."
        labels = {n.id: n.label for n in self.nodes}
        lines = []
        for type_ in NodeType:
            nodes = self.of_type(type_)
            if nodes:
                items = ", ".join(n.label + (f" ({n.detail})" if n.detail else "") for n in nodes)
                lines.append(f"{type_.value.title()}s: {items}")
        for e in self.edges:
            lines.append(
                f"{labels.get(e.source, e.source)} {e.relation.value} {labels.get(e.target, e.target)}"
            )
        for domain, note in self.domains.items():
            lines.append(f"Known about {domain.value}: {note}")
        return "\n".join(lines)


# What the graph-builder agent returns. All fields required to keep the model's JSON strict.
class NodeIn(BaseModel):
    type: NodeType
    label: str = Field(
        description="Short, 1-4 words. Reuse an existing label exactly if it is the same thing."
    )
    detail: str = Field(description="Optional short detail in the person's words, or empty")
    severity: int = Field(ge=0, le=3, description="Issues only: 0 unknown, 1 mild, 2 moderate, 3 severe")


class EdgeIn(BaseModel):
    source_type: NodeType
    source_label: str
    target_type: NodeType
    target_label: str
    relation: Relation


class DomainNote(BaseModel):
    domain: Domain
    note: str = Field(description="What the person said about this area, in a few words")


class GraphUpdate(BaseModel):
    nodes: list[NodeIn]
    edges: list[EdgeIn]
    domains: list[DomainNote]

    @classmethod
    def empty(cls) -> "GraphUpdate":
        return cls(nodes=[], edges=[], domains=[])
