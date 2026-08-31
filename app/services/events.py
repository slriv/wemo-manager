"""Thread-safe device-change notifications for SSE clients."""

from __future__ import annotations

import asyncio


class DeviceEventBroadcaster:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue[None]] = set()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Record the running event loop so emit() can be called from any thread."""
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[None]:
        """Caller must unsubscribe() when done."""
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[None]) -> None:
        self._subscribers.discard(queue)

    def emit(self) -> None:
        """Thread-safe."""
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._emit_on_loop)

    def _emit_on_loop(self) -> None:
        for queue in self._subscribers:
            if queue.full():
                continue  # Signal already queued.
            queue.put_nowait(None)


device_events = DeviceEventBroadcaster()
