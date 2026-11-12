from __future__ import annotations

import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    """In-process WebSocket fan-out keyed by user id.

    Cross-process updates are delivered by the polling loop in the realtime
    endpoint, which reads authoritative state from the database. This keeps
    progress correct even though workers run in separate processes.
    """

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[user_id].add(websocket)

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, payload: dict) -> None:
        sockets = list(self._connections.get(user_id, ()))
        dead: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_text(json.dumps(payload, default=str))
            except Exception:
                dead.append(socket)
        for socket in dead:
            await self.disconnect(user_id, socket)

    def connection_count(self) -> int:
        return sum(len(items) for items in self._connections.values())


manager = ConnectionManager()
