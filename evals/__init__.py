"""Safety evaluation for Solace.

Two suites, both run against the real pipeline:
- risk:    does the risk screen (keywords + AI screener) rate each message correctly?
- replies: do whole conversations get safe, human replies? Scored by an AI judge plus hard checks.

    uv run python -m evals            # everything (needs OPENAI_API_KEY; costs a little)
    uv run python -m evals risk       # one suite
"""

import json
from pathlib import Path

DATA = Path(__file__).parent / "data"
REPORTS = Path(__file__).parent / "reports"
LEVELS = ["none", "low", "moderate", "high", "imminent"]
INFORMATIONAL_TAGS = {"sinhala"}  # reported, but not yet required to pass


def load(name: str) -> list[dict]:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def level_index(name: str) -> int:
    return LEVELS.index(name)
