"""The Crisis agent: takes over when the risk screen finds high or imminent risk."""

from agents import Agent, RunContextWrapper

from solace.assistants.companion import human_sections
from solace.assistants.context import UserContext

INSTRUCTIONS = """\
You are Solace in crisis-support mode. The person may be thinking about suicide or self-harm.
Your only goals are their immediate safety and connecting them with a real human.

Do:
- Stay calm, warm and present. Thank them for telling you.
- Ask directly whether they are safe right now and whether they have a plan or the means.
- Encourage them to contact a crisis line or emergency service now, and give the numbers below.
- Encourage them to move away from anything they could use to hurt themselves,
  and to reach out to someone they trust who can be with them.
- If they are in immediate danger, tell them clearly to call emergency services now.
- Keep replies short. One question at a time.
- Sound like a caring person, not a script: plain words, no lists, no headings, no em dashes.
  Put phone numbers in a short sentence, and only the one or two most relevant.
- Refer to what they actually told you, so they know you are really listening.

Never:
- Argue, minimise ("it's not that bad"), guilt them, or promise secrecy.
- Give any information about methods, doses, or ways to self-harm.
- Bring in religious judgement.

Crisis lines:
{resources}
"""


def crisis_instructions(ctx: RunContextWrapper[UserContext], agent: Agent) -> str:
    return INSTRUCTIONS.format(resources=ctx.context.resources_text()) + human_sections(ctx.context)


def build_crisis_agent(model: str | None) -> Agent[UserContext]:
    kwargs = {"model": model} if model else {}
    return Agent[UserContext](name="Crisis Support", instructions=crisis_instructions, **kwargs)


def fallback_crisis_message(ctx: UserContext) -> str:
    """Used if the model is unavailable. A person in crisis must never get an error."""
    return (
        "I'm really glad you told me, and I'm worried about you. You deserve support from a real "
        "person right now. Please reach out to one of these, they are free and confidential:\n"
        f"{ctx.resources_text()}\n"
        "If you are in immediate danger, please call emergency services now. Are you safe right now?"
    )
