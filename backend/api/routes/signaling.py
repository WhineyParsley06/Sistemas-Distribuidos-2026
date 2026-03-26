from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.api.contracts.signaling_v1 import (
    SIGNAL_MESSAGE_DISCONNECT,
    SIGNAL_MESSAGE_ERROR,
    SIGNAL_MESSAGE_PING,
    SIGNAL_MESSAGE_PONG,
    SUPPORTED_SIGNAL_TYPES,
)
from backend.container import signaling_manager

router = APIRouter(tags=["signaling"])


@router.websocket("/signal/ws")
async def signaling_websocket_endpoint(websocket: WebSocket, username: str = "Peer") -> None:
    username = await signaling_manager.connect(websocket, username)

    try:
        while True:
            try:
                data = await websocket.receive_json()

                if not isinstance(data, dict):
                    await websocket.send_json(
                        {
                            "type": SIGNAL_MESSAGE_ERROR,
                            "message": "Payload de señalización inválido",
                        }
                    )
                    continue

                msg_type = (data.get("type") or "").strip()

                if msg_type == SIGNAL_MESSAGE_DISCONNECT:
                    break

                if msg_type == SIGNAL_MESSAGE_PING:
                    await websocket.send_json(
                        {
                            "type": SIGNAL_MESSAGE_PONG,
                            "timestamp": data.get("timestamp"),
                        }
                    )
                    continue

                if msg_type not in SUPPORTED_SIGNAL_TYPES:
                    await websocket.send_json(
                        {
                            "type": SIGNAL_MESSAGE_ERROR,
                            "message": f"Tipo de mensaje de señalización no soportado: {msg_type}",
                        }
                    )
                    continue

                destination = (data.get("to") or "").strip()
                payload = data.get("payload")
                if not destination:
                    await websocket.send_json(
                        {
                            "type": SIGNAL_MESSAGE_ERROR,
                            "message": "Destino de señalización requerido",
                        }
                    )
                    continue

                ok = await signaling_manager.send_to(
                    destination,
                    {
                        "type": msg_type,
                        "from": username,
                        "payload": payload,
                    },
                )
                if not ok:
                    await websocket.send_json(
                        {
                            "type": SIGNAL_MESSAGE_ERROR,
                            "message": f"Peer '{destination}' no disponible",
                        }
                    )
            except Exception as exc:
                try:
                    await websocket.send_json(
                        {
                            "type": SIGNAL_MESSAGE_ERROR,
                            "message": f"Error procesando señalización: {exc}",
                        }
                    )
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    finally:
        await signaling_manager.disconnect(websocket)
