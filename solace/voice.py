"""Real-time voice: the browser talks to OpenAI's Realtime API directly over WebRTC.

Our server never relays audio. It does three things:
1. mints a short-lived key so the real API key never reaches the browser,
2. writes the spoken instructions (same companion / crisis rules as text, tuned for speech),
3. screens every finished user transcript for risk, saves both sides to the conversation,
   and tells the browser to switch to crisis instructions when needed.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from openai import AsyncOpenAI

from solace.config import Settings

Mint = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

SPOKEN = """
# You are speaking out loud, in a live voice call
- Sound like a warm, unhurried person on the phone. Short sentences. Natural pauses are fine.
- Keep most turns to one to three sentences, then let them talk. Never monologue.
- Never read out lists, links, headings or symbols.
- Say phone numbers slowly, digit by digit, for example "one, nine, two, six".
- If you didn't catch something, say so simply and ask them to repeat it.
- If they go quiet, it's fine to wait, or gently check in.
- Speak English unless they speak another language, then follow them.
"""


OPENING = """
# The call is just starting
Open with one short, warm sentence, like a friend picking up the phone. If you were already
talking (see the conversation so far), gently pick up where you left off instead of starting over.
"""


def voice_instructions(base: str, opening: bool = False) -> str:
    return base + SPOKEN + (OPENING if opening else "")


def session_config(settings: Settings, instructions: str) -> dict[str, Any]:
    return {
        "type": "realtime",
        "model": settings.solace_voice_model,
        "instructions": instructions,
        "audio": {
            "input": {
                "transcription": {"model": settings.solace_transcribe_model, "language": "en"},
                # Semantic VAD waits for a natural end of thought, so people aren't cut off mid-sentence.
                "turn_detection": {"type": "semantic_vad", "eagerness": "low"},
                "noise_reduction": {"type": "near_field"},
            },
            "output": {"voice": settings.solace_voice},
        },
    }


def openai_minter(settings: Settings) -> Mint:
    async def mint(session: dict[str, Any]) -> dict[str, Any]:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        secret = await client.realtime.client_secrets.create(
            expires_after={"anchor": "created_at", "seconds": 600}, session=session
        )
        return {"value": secret.value, "expires_at": secret.expires_at}

    return mint
