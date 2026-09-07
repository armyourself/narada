"""Sender-side relay selection policy (Phase 4).

The sender's ``NaradaAdapter`` asks :class:`RelaySelector` for one
or more peers to deposit an envelope with when the recipient is not
directly reachable.

Selection order:

1. **V2 mailbox-discovery hint.** If the recipient's public id carries
   a ``node_id_hint`` TLV (``protocol/identity.md``) and the hinted
   node is in the ``PeerBook`` and not marked ``down``, return it.
2. **Peer book fallback.** Otherwise return a peer sorted by
   ``(down=False first, last_seen desc, missed_pings asc)``,
   excluding peers that were tried within ``cooldown_seconds``.

Selection is deterministic for a given ``PeerBook`` snapshot so
sending the same envelope twice in quick succession does not pick
different relays back-to-back.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Iterable, Optional, Protocol

# V2 public id hint TLV regex. Matches a TLV of type 0x01 followed by
# a 1-byte length (1..6) and a bech32m node id (4..40 chars).
_HINT_RE = re.compile(
    rb"\x01"  # TLV type 0x01
    rb"(?P<length>[\x01-\x32])"  # 1..50 bytes for a bech32m node id
    rb"(?P<value>[A-Z2-7a-z]{4,50})",
    re.ASCII | re.IGNORECASE,
)

class _PeerLike(Protocol):
    endpoint: str
    last_seen: float
    down: bool
    missed_pings: int


class PeerBookLike(Protocol):
    def all(self) -> list: ...
    def get(self, endpoint: str): ...
    def live_endpoints(self) -> list: ...


@dataclass(frozen=True)
class SelectedRelay:
    """One peer selected as a relay candidate."""

    endpoint: str
    node_id: Optional[str]  # node1... if known; may be None
    reason: str  # "hint" | "fallback"


class RelaySelector:
    """Pick a relay endpoint for a given envelope recipient."""

    def __init__(
        self,
        *,
        cooldown_seconds: int = 300,
        now: Optional[callable] = None,
    ) -> None:
        self._cooldown = int(cooldown_seconds)
        self._clock = now or time.time
        self._lock = threading.RLock()
        # endpoint -> last_attempt_ts (epoch seconds)
        self._attempts: dict[str, float] = {}

    def note_attempt(self, endpoint: str) -> None:
        """Mark ``endpoint`` as just-attempted so cooldown applies."""
        with self._lock:
            self._attempts[endpoint] = self._clock()

    def forget(self, endpoint: str) -> None:
        with self._lock:
            self._attempts.pop(endpoint, None)

    def cooldown_active(self, endpoint: str) -> bool:
        with self._lock:
            ts = self._attempts.get(endpoint)
        if ts is None:
            return False
        return (self._clock() - ts) < self._cooldown

    # --- Selection ----------------------------------------------------

    def select(
        self,
        *,
        peer_book: PeerBookLike,
        recipient_public_id: str,
        exclude_endpoints: Optional[Iterable[str]] = None,
    ) -> Optional[SelectedRelay]:
        excluded = set(exclude_endpoints or ())
        # 1. V2 hint
        hint = _extract_node_id_hint(recipient_public_id)
        if hint is not None:
            for state in peer_book.all():
                if getattr(state, "node_id", None) == hint:
                    if not getattr(state, "down", False):
                        endpoint = state.endpoint
                        if endpoint in excluded or self.cooldown_active(endpoint):
                            break
                        return SelectedRelay(
                            endpoint=endpoint, node_id=hint, reason="hint"
                        )
                    break
        # 2. Peer book fallback
        live = [
            s for s in peer_book.all() if not getattr(s, "down", False)
        ]
        live.sort(
            key=lambda s: (
                -(getattr(s, "last_seen", 0.0)),
                getattr(s, "missed_pings", 0),
            )
        )
        for state in live:
            endpoint = getattr(state, "endpoint", None)
            if not endpoint:
                continue
            if endpoint in excluded:
                continue
            if self.cooldown_active(endpoint):
                continue
            return SelectedRelay(
                endpoint=endpoint,
                node_id=getattr(state, "node_id", None),
                reason="fallback",
            )
        return None


def _extract_node_id_hint(public_id: str) -> Optional[str]:
    """Return the embedded ``node_id_hint`` TLV if present.

    The hint lives in the V2 public id payload as a single TLV
    (type 0x01, length 1..50 bytes) followed by a bech32m-encoded
    node id. We use a regex to find the TLV header and then take
    exactly ``length`` bytes as the node-id hint; the bech32m
    charset overlaps the ASCII alphabet but not every byte, so a
    raw regex match is not enough to bound the value.

    Returns ``None`` for V1 ids and for V2 ids without the TLV.
    """
    try:
        raw = public_id.encode("ascii")
    except UnicodeEncodeError:
        return None
    m = _HINT_RE.search(raw)
    if m is None:
        return None
    length = m.group("length")
    if length is None:
        return None
    try:
        n = length[0]
    except IndexError:
        return None
    value_start = m.end("length")
    if value_start + n > len(raw):
        return None
    candidate = raw[value_start : value_start + n]
    try:
        return candidate.decode("ascii")
    except UnicodeDecodeError:
        return None


__all__ = [
    "RelaySelector",
    "SelectedRelay",
]
