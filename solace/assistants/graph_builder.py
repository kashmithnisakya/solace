"""The Graph Builder: reads each message and updates the person's issue graph."""

from agents import Agent

from solace.graph import GraphUpdate

INSTRUCTIONS = """\
You maintain a private map of what a person is going through, for a mental-health support app.
You never talk to the person. You read their LATEST message, plus the current map, and return
only what is NEW or CHANGED. Return empty lists if nothing new was said.

Node types:
- issue: a problem or difficulty (exam stress, debt, breakup, poor sleep, conflict with father)
- emotion: a feeling (sadness, guilt, anger, fear, loneliness)
- trigger: something that sets it off (nights alone, social media, arguments)
- person: someone involved (mother, best friend, boss). Use roles, NEVER real names.
- support: something or someone that helps (sister, prayer, football, music)
- strength: a personal strength you can see (caring, hardworking, honest)

Relations: causes, worsens, related_to, helps_with. Only connect nodes the person actually linked,
or that you are adding in this same update or that already exist in the map.

Domains: if the message tells you about one of these areas, add a short note:
onset (when it started / how long), mood, interest (enjoyment of things), sleep, appetite, energy,
concentration, self_worth, anxiety, support (who they can turn to), functioning (work, study, daily life).

Rules:
- Use the person's own meaning. Do not invent, diagnose, or guess.
- Labels are short (1-4 words), lowercase, no names, no phone numbers, no addresses.
- If something already exists in the map, reuse its label exactly.
- Write labels in the language the person writes in (Sinhala script for Sinhala or romanised Sinhala,
  in everyday words). Domain notes can be in English: only counsellors read them.
- Issue severity: 0 unknown, 1 mild, 2 moderate, 3 severe, based only on what they said.
"""


def build_graph_builder(model: str | None) -> Agent:
    kwargs = {"model": model} if model else {}
    return Agent(name="Graph Builder", instructions=INSTRUCTIONS, output_type=GraphUpdate, **kwargs)


def builder_input(graph_summary: str, message: str) -> str:
    return f"Current map:\n{graph_summary}\n\nLatest message from the person:\n{message}"
