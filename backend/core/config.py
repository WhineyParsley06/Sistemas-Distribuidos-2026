from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("CHAT_HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", os.getenv("CHAT_PORT", "8000")))
    transport_mode: str = "p2p"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
