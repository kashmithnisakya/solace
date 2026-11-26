"""Per-conversation context passed to every agent."""

from dataclasses import dataclass, field

from solace.safety import Resource


@dataclass
class UserContext:
    # The faith tradition the person chose to draw on, or None. Never assumed.
    faith: str | None = None
    region: str = "LK"
    resources: list[Resource] = field(default_factory=list)

    def resources_text(self) -> str:
        return "\n".join(f"- {r.name}: {r.contact} ({r.description})" for r in self.resources)
