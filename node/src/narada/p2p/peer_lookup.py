"""Peer-lookup client (Phase 3 commit 4).

The :class:`PeerLookupClient` knows how to ask a peer Narada node
"do you host this user?" and parse the reply. The wire protocol is
intentionally tiny:

  request:  {"type": "directory.lookup", "public_id": "narada1..."}
  response: {"type": "directory.lookup.result",
             "entry": null}
             OR
             {"type": "directory.lookup.result",
             "entry": {"public_id": "narada1...",
                       "base_url": "host:port",
                       "account_id": "alice@example.com"}}

A real QUIC implementation lands in commit 5 alongside the
inbound listener. Until then, :class:`InMemoryPeerLookupClient`
covers tests and CLI scripts that already know the answer.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Optional

from src.narada_identity.errors import NaradaIdentityError

log = logging.getLogger("narada.p2p.peer_lookup")


@dataclass(frozen=True)
class DirectoryEntry:
    public_id: str
    base_url: str
    account_id: str


class InMemoryPeerLookupClient:
    """Test/CLI peer-lookup client with a hand-coded answer table."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # node_id -> {public_id -> DirectoryEntry}
        self._by_node: dict[str, dict[str, DirectoryEntry]] = {}
        # public_id -> list[(node_id, DirectoryEntry)] for ask_all fallback
        self._by_public: dict[str, list[tuple[str, DirectoryEntry]]] = {}

    def publish(self, *, node_id: str, entry: DirectoryEntry) -> None:
        with self._lock:
            self._by_node.setdefault(node_id, {})[entry.public_id] = entry
            self._by_public.setdefault(entry.public_id, []).append(
                (node_id, entry)
            )

    def ask_node(
        self, node_id: str, public_id: str
    ) -> Optional[tuple[str, str, str, str]]:
        """Return ``(public_id, base_url, account_id, ack_node_id)``.

        ``ack_node_id`` is the node id that *signed* the response.
        Mitigates threat T2: a directory client can refuse an answer
        where the peer claims to host a user but signs as a
        different node.
        """
        with self._lock:
            entries = self._by_node.get(node_id, {})
            entry = entries.get(public_id)
            if entry is None:
                return None
            return (entry.public_id, entry.base_url, entry.account_id, node_id)

    def ask_all(self, public_id: str) -> list[Optional[tuple[str, str, str, str]]]:
        with self._lock:
            pairs = list(self._by_public.get(public_id, []))
        out: list[Optional[tuple[str, str, str, str]]] = []
        for nid, entry in pairs:
            out.append((entry.public_id, entry.base_url, entry.account_id, nid))
        return out


class NoopPeerLookupClient:
    def ask_node(
        self, node_id: str, public_id: str
    ) -> Optional[tuple[str, str, str, str]]:
        return None

    def ask_all(self, public_id: str) -> list[Optional[tuple[str, str, str, str]]]:
        return []


__all__ = [
    "DirectoryEntry",
    "InMemoryPeerLookupClient",
    "NoopPeerLookupClient",
]
