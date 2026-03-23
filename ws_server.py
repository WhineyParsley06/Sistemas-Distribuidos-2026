from __future__ import annotations

import asyncio
import os
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

HOST = os.getenv("CHAT_HOST", "0.0.0.0")
PORT = int(os.getenv("CHAT_PORT", "8000"))

app = FastAPI(title="Chat WebSocket API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    def __init__(self) -> None:
        self.users: Dict[str, WebSocket] = {}
        self.sockets: Dict[WebSocket, str] = {}
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, username: str) -> str:
        await websocket.accept()

        async with self.lock:
            final_name = username.strip() or "Usuario"
            if final_name in self.users:
                suffix = 2
                base = final_name
                while f"{base}_{suffix}" in self.users:
                    suffix += 1
                final_name = f"{base}_{suffix}"

            self.users[final_name] = websocket
            self.sockets[websocket] = final_name

        await websocket.send_json(
            {
                "type": "system",
                "message": f"Conectado como {final_name}",
                "username": final_name,
            }
        )
        await self.broadcast_user_list()
        return final_name

    async def disconnect(self, websocket: WebSocket) -> str | None:
        async with self.lock:
            username = self.sockets.pop(websocket, None)
            if username:
                self.users.pop(username, None)
        if username:
            await self.broadcast(
                {
                    "type": "user_disconnected",
                    "username": username,
                    "message": f"{username} se ha desconectado",
                }
            )
            await self.broadcast_user_list()
        return username

    async def broadcast(self, payload: dict) -> None:
        async with self.lock:
            items = list(self.users.items())

        for username, ws in items:
            try:
                await ws.send_json(payload)
            except Exception:
                await self.disconnect(ws)

    async def broadcast_user_list(self) -> None:
        async with self.lock:
            usernames = list(self.users.keys())
            sockets = list(self.users.values())

        payload = {"type": "user_list", "users": usernames}
        for ws in sockets:
            try:
                await ws.send_json(payload)
            except Exception:
                await self.disconnect(ws)

    async def send_to(self, destination: str, payload: dict) -> bool:
        async with self.lock:
            ws = self.users.get(destination)

        if ws is None:
            return False

        try:
            await ws.send_json(payload)
            return True
        except Exception:
            await self.disconnect(ws)
            return False


manager = ConnectionManager()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "connected_users": list(manager.users.keys())}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, username: str = "Usuario") -> None:
    username = await manager.connect(websocket, username)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "text":
                destination = (data.get("to") or "").strip()
                message = (data.get("message") or "").strip()
                if not destination or not message:
                    continue

                ok = await manager.send_to(
                    destination,
                    {
                        "type": "text",
                        "from": username,
                        "message": message,
                    },
                )
                if not ok:
                    await websocket.send_json(
                        {
                            "type": "system",
                            "message": f"Usuario '{destination}' no disponible",
                        }
                    )

            elif msg_type == "file":
                destination = (data.get("to") or "").strip()
                filename = (data.get("filename") or "archivo.bin").strip()
                content = data.get("content") or ""
                mime_type = data.get("mimeType") or "application/octet-stream"
                size = int(data.get("size") or 0)

                if not destination or not content:
                    continue

                ok = await manager.send_to(
                    destination,
                    {
                        "type": "file",
                        "from": username,
                        "filename": filename,
                        "content": content,
                        "mimeType": mime_type,
                        "size": size,
                    },
                )
                if not ok:
                    await websocket.send_json(
                        {
                            "type": "system",
                            "message": f"Usuario '{destination}' no disponible",
                        }
                    )

            elif msg_type == "disconnect":
                break

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json(
                {
                    "type": "system",
                    "message": f"Error interno del servidor: {exc}",
                }
            )
        except Exception:
            pass
    finally:
        await manager.disconnect(websocket)


# Servir archivos estáticos del frontend
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")

if os.path.exists(frontend_dist):
    # Ruta raíz
    @app.get("/")
    async def root():
        return FileResponse(os.path.join(frontend_dist, "index.html"))
    
    # Montar carpeta de assets
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")
    
    # Montar raíz como archivos estáticos
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ws_server:app", host=HOST, port=PORT, reload=True)
