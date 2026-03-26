from __future__ import annotations

from typing import Final

SIGNALING_CONTRACT_VERSION: Final[str] = "signaling-v1"

SIGNAL_MESSAGE_REGISTERED: Final[str] = "signal_registered"
SIGNAL_MESSAGE_PEER_LIST: Final[str] = "signal_peer_list"
SIGNAL_MESSAGE_OFFER: Final[str] = "signal_offer"
SIGNAL_MESSAGE_ANSWER: Final[str] = "signal_answer"
SIGNAL_MESSAGE_ICE_CANDIDATE: Final[str] = "signal_ice_candidate"
SIGNAL_MESSAGE_ERROR: Final[str] = "signal_error"
SIGNAL_MESSAGE_DISCONNECT: Final[str] = "signal_disconnect"
SIGNAL_MESSAGE_PING: Final[str] = "signal_ping"
SIGNAL_MESSAGE_PONG: Final[str] = "signal_pong"

SUPPORTED_SIGNAL_TYPES: Final[set[str]] = {
    SIGNAL_MESSAGE_OFFER,
    SIGNAL_MESSAGE_ANSWER,
    SIGNAL_MESSAGE_ICE_CANDIDATE,
    SIGNAL_MESSAGE_DISCONNECT,
    SIGNAL_MESSAGE_PING,
}
