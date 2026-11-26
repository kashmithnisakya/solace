"""Risk levels and how to combine assessments from different detectors."""

from enum import IntEnum

from pydantic import BaseModel, Field


class RiskLevel(IntEnum):
    NONE = 0
    LOW = 1  # distress, but no sign of self-harm
    MODERATE = 2  # hopelessness, passive wishes to not exist
    HIGH = 3  # thoughts of suicide or self-harm
    IMMINENT = 4  # plan, means, timeline, or an attempt in progress


class RiskAssessment(BaseModel):
    level: RiskLevel = RiskLevel.NONE
    reasons: list[str] = Field(default_factory=list)
    source: str = "none"

    @property
    def is_crisis(self) -> bool:
        return self.level >= RiskLevel.HIGH

    @property
    def show_resources(self) -> bool:
        return self.level >= RiskLevel.MODERATE


def combine(*assessments: RiskAssessment) -> RiskAssessment:
    """Take the most severe assessment. Detectors can only raise risk, never lower it."""
    worst = max(assessments, key=lambda a: a.level)
    reasons = [r for a in assessments for r in a.reasons]
    sources = "+".join(a.source for a in assessments if a.level > RiskLevel.NONE) or "none"
    return RiskAssessment(level=worst.level, reasons=reasons, source=sources)
