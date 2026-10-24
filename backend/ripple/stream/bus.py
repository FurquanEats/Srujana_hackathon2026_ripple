"""In-process publish/subscribe for stream events. Each WebSocket client gets its own bounded queue; a slow client
loses its oldest events instead of slowing the engine down."""

from __future__ import annotations

import asyncio
from typing import Any


class EventBus:
    def __init__(self, maxsize: int = 1000) -> None:
        self.maxsize = maxsize
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self.maxsize)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: dict[str, Any]) -> None:
        for queue in self._subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    @property
    def subscribers(self) -> int:
        return len(self._subscribers)
