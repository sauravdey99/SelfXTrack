"""WebSocket fan-out of live events (location updates, SOS) to app users."""
import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._conns: dict[int, set[WebSocket]] = defaultdict(set)
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self._conns[user_id].add(ws)

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        self._conns[user_id].discard(ws)

    async def _send(self, user_id: int, message: dict) -> None:
        dead = []
        for ws in list(self._conns.get(user_id, ())):
            try:
                await ws.send_text(json.dumps(message, default=str))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)

    def publish(self, user_ids: list[int], message: dict) -> None:
        """Thread-safe publish (works from sync request handlers and the MQTT thread)."""
        if self.loop is None:
            return
        for uid in user_ids:
            if uid in self._conns:
                asyncio.run_coroutine_threadsafe(self._send(uid, message), self.loop)


manager = ConnectionManager()
