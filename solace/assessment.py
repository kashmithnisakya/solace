"""Assessment: decide which area of someone's life is worth gently asking about next.

This is not a questionnaire and not a diagnosis. It gives the Companion one optional
suggestion per turn, based on what the issue graph does not cover yet.
"""

from pydantic import BaseModel

from solace.graph import Domain, IssueGraph, NodeType


class Gap(BaseModel):
    domain: Domain
    hint: str


# Order matters: most useful first.
_HINTS: list[tuple[Domain, str]] = [
    (Domain.ONSET, "when this started, or how long it has been going on"),
    (Domain.SUPPORT, "who they can talk to or lean on"),
    (Domain.SLEEP, "how they have been sleeping"),
    (Domain.MOOD, "how their mood has been most days"),
    (Domain.FUNCTIONING, "how it affects their work, study, family or daily tasks"),
    (Domain.INTEREST, "whether they still enjoy things they used to like"),
    (Domain.ENERGY, "their energy levels"),
    (Domain.APPETITE, "their eating and appetite"),
    (Domain.ANXIETY, "whether they feel worried, tense or on edge"),
    (Domain.CONCENTRATION, "whether it is hard to focus"),
    (Domain.SELF_WORTH, "how they have been feeling about themselves"),
]

# Wait until the person has shared something before asking about anything.
MIN_NODES = 1


def next_gap(graph: IssueGraph) -> Gap | None:
    if len(graph.of_type(NodeType.ISSUE)) + len(graph.of_type(NodeType.EMOTION)) < MIN_NODES:
        return None
    for domain, hint in _HINTS:
        if domain not in graph.domains:
            if domain == Domain.SUPPORT and graph.of_type(NodeType.SUPPORT):
                continue  # they already mentioned someone or something that helps
            return Gap(domain=domain, hint=hint)
    return None


def coverage(graph: IssueGraph) -> float:
    return len(graph.domains) / len(_HINTS)
