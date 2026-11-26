"""LLM risk classifier. Reads the latest message in context and rates suicide/self-harm risk."""

from agents import Agent, ModelSettings
from pydantic import BaseModel, Field

from solace.safety.risk import RiskLevel

INSTRUCTIONS = """\
You are a clinical safety screener for a mental-health support app. You never talk to the user.
Rate the risk of suicide or self-harm in the user's LATEST message, using earlier messages as context.

Levels:
0 none: no distress, or ordinary everyday stress.
1 low: sadness, anxiety, stress or loneliness, with no sign of self-harm.
2 moderate: hopelessness, feeling like a burden, passive wishes to not exist or not wake up.
3 high: thoughts of suicide or self-harm, current or very recent self-harm.
4 imminent: a plan, a method, access to means, a time, saying goodbye, or an attempt in progress.

Rules:
- Indirect, coded, or joking language still counts ("unalive", "kms", "I'll just sleep forever").
- When unsure between two levels, choose the higher one.
- Talking about someone else at risk (a friend, a child) is level 3 so the user gets resources.
- Give short reasons that quote or paraphrase the message.
"""


class RiskOutput(BaseModel):
    level: int = Field(ge=0, le=4, description="Risk level 0-4")
    reasons: list[str] = Field(default_factory=list)

    def risk_level(self) -> RiskLevel:
        return RiskLevel(self.level)


def build_classifier(model: str | None) -> Agent:
    kwargs = {"model": model} if model else {}
    return Agent(
        name="Risk Screener",
        instructions=INSTRUCTIONS,
        output_type=RiskOutput,
        model_settings=ModelSettings(),
        **kwargs,
    )
