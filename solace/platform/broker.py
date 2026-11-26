"""In-process live updates (server-sent events) between people and counsellors.

Single-process only. When running several workers, replace this with a shared broker such as
Redis pub/sub, keeping the same publish / subscribe interface.
"""

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

COUNSELLORS = "counsellors"


def person(session_id: str) -> str:
    return f"session:{session_id}"


class Broker:
    def __init__(self) -> None:
        self._subs: dict[str, dict[asyncio.Queue, str | None]] = defaultdict(dict)

    def publish(self, channel: str, event: dict[str, Any]) -> None:
        for q in list(self._subs.get(channel, {})):
            if q.qsize() < 100:  # a stuck client must not grow memory forever
                q.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self, channel: str, who: str | None = None) -> AsyncIterator[asyncio.Queue]:
        q: asyncio.Queue = asyncio.Queue()
        self._subs[channel][q] = who
        try:
            yield q
        finally:
            self._subs[channel].pop(q, None)
            if not self._subs[channel]:
                del self._subs[channel]

    def present(self, channel: str) -> set[str]:
        """Who is listening on a channel (e.g. which counsellors have the dashboard open)."""
        return {w for w in self._subs.get(channel, {}).values() if w}


broker = Broker()
