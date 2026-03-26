from __future__ import annotations

import asyncio
from typing import Dict

from fastapi import WebSocket

from backend.api.contracts.signaling_v1 import (
    SIGNAL_MESSAGE_PEER_LIST,
    SIGNAL_MESSAGE_REGISTERED,
)


class SignalingManager:
    def __init__(self) -> None:
        self.peers: Dict[str, WebSocket] = {}
        self.sockets: Dict[WebSocket, str] = {}
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, username: str) -> str:
        await websocket.accept()

        async with self.lock:
            final_name = username.strip() or "Peer"
            if final_name in self.peers:
                suffix = 2
                base = final_name
                while f"{base}_{suffix}" in self.peers:
                    suffix += 1
                final_name = f"{base}_{suffix}"

            self.peers[final_name] = websocket
            self.sockets[websocket] = final_name

        await websocket.send_json(
            {
                "type": SIGNAL_MESSAGE_REGISTERED,
                "username": final_name,
            }
        )
        await self.broadcast_peer_list()
        return final_name

    async def disconnect(self, websocket: WebSocket) -> str | None:
        async with self.lock:
            username = self.sockets.pop(websocket, None)
            if username:
                self.peers.pop(username, None)

        await self.broadcast_peer_list()
        return username

    async def broadcast_peer_list(self) -> None:
        async with self.lock:
            usernames = list(self.peers.keys())
            sockets = list(self.peers.values())

        payload = {"type": SIGNAL_MESSAGE_PEER_LIST, "users": usernames}
        for ws in sockets:
            try:
                await ws.send_json(payload)
            except Exception:
                await self.disconnect(ws)

    async def send_to(self, destination: str, payload: dict) -> bool:
        async with self.lock:
            ws = self.peers.get(destination)

        if ws is None:
            return False

        try:
            await ws.send_json(payload)
            return True
        except Exception:
            await self.disconnect(ws)
            return False
