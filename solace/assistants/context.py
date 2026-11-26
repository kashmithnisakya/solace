"""Per-conversation context passed to every agent."""

from dataclasses import dataclass, field

from solace.knowledge import Passage
from solace.safety import Resource


@dataclass
class UserContext:
    # The faith tradition the person chose to draw on, or None. Never assumed.
    faith: str | None = None
    region: str = "LK"
    resources: list[Resource] = field(default_factory=list)
    # What the issue graph knows so far, as text for the prompt.
    graph_summary: str = "Nothing known yet."
    # One area worth gently asking about next, or None.
    next_gap: str | None = None
    # Knowledge base notes relevant to this message (never used in crisis mode).
    knowledge: list[Passage] = field(default_factory=list)
    # True in voice calls: no citation markers in speech.
    spoken: bool = False
    # True while the person is waiting for a human counsellor to join.
    waiting_for_human: bool = False
    # The language to reply in when the message doesn't make it clear: "en" or "si".
    language: str = "en"

    def resources_text(self) -> str:
        return "\n".join(f"- {r.name}: {r.contact} ({r.description})" for r in self.resources)
