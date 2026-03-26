from fastapi import APIRouter

from backend.api.contracts.signaling_v1 import SIGNALING_CONTRACT_VERSION
from backend.container import signaling_manager
from backend.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "connected_users": list(signaling_manager.peers.keys()),
        "transport_mode": settings.transport_mode,
        "contract_version": SIGNALING_CONTRACT_VERSION,
    }
