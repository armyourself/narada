"""Distributed routing for the Narada directory (Phase 3 commit 4).

The base :class:`src.narada.directory.NaradaDirectory` is local-only.
This module wraps it with two layers that make routing work across
the network:

* :class:`CachingDirectory` -- TTL cache on top of any directory.
  Cache hits cost nothing; cache misses fall through to the inner
  directory.

* :class:`DistributedDirectory` -- peer-ask fallback. On a miss, ask
  every known peer (via the QUIC transport) whether they host the
  recipient. The first peer that says yes wins; the answer is cached.

Both layers honour V2 node-id hints (commit 3): if the recipient's
``narada1...`` public id carries an embedded ``node1...`` hint, the
lookup is sent directly to that node instead of being broadcast.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Protocol

from src.narada.directory import NaradaDirectory
from src.narada_identity.encoding import decode_node_hint

log = logging.getLogger("narada.routing")

_DEFAULT_TTL_SECONDS = 5 * 60


class _PeerClientLike(Protocol):
    """Structural type for the peer-lookup client used by DistributedDirectory.

    Production code passes a real QUIC-backed implementation. Tests
    pass a stub.
    """

    def ask_node(self, node_id: str, public_id: str) -> Optional[tuple[str, str, str]]:
        ...

    def ask_all(self, public_id: str) -> list[Optional[tuple[str, str, str]]]:
        ...


class PeerLookupError(Exception):
    """Raised by a PeerLookupClient on transport failure."""


class CachingDirectory(NaradaDirectory):
    """Read-through TTL cache that wraps another directory."""

    def __init__(
        self,
        inner: NaradaDirectory,
        *,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        self._inner = inner
        self._ttl = ttl_seconds
        self._lock = threading.RLock()
        self._cache: dict[str, tuple[float, str]] = {}

    def lookup(self, public_id: str) -> Optional[str]:
        now = time.time()
        with self._lock:
            entry = self._cache.get(public_id)
            if entry is not None and entry[0] >= now:
                return entry[1]
            if entry is not None:
                del self._cache[public_id]
        result = self._inner.lookup(public_id)
        if result is not None:
            with self._lock:
                self._cache[public_id] = (time.time() + self._ttl, result)
        return result

    def add(self, public_id: str, base_url: str, account_id: str) -> None:
        self._inner.add(public_id, base_url, account_id)
        with self._lock:
            self._cache[public_id] = (time.time() + self._ttl, base_url)

    def remove(self, public_id: str) -> bool:
        with self._lock:
            self._cache.pop(public_id, None)
        return self._inner.remove(public_id)

    def all_entries(self) -> list[tuple[str, str, str]]:
        return self._inner.all_entries()

    def invalidate(self, public_id: Optional[str] = None) -> None:
        with self._lock:
            if public_id is None:
                self._cache.clear()
            else:
                self._cache.pop(public_id, None)


class DistributedDirectory(NaradaDirectory):
    """Peer-ask fallback layered on a local directory.

    On a miss in the inner directory, the wrapper:

    1. Inspects the recipient's public id for a V2 node-id hint. If
       present, asks that node first.
    2. Otherwise, asks every known peer (via a PeerLookupClient).

    Successful answers are written back to the inner directory so
    the next lookup is a cache hit.
    """

    def __init__(
        self,
        inner: NaradaDirectory,
        *,
        peer_client: _PeerClientLike,
    ) -> None:
        self._inner = inner
        self._peer = peer_client

    def _consult_hint(self, public_id: str) -> Optional[str]:
        hint = decode_node_hint(public_id)
        if not hint:
            return None
        try:
            answer = self._peer.ask_node(hint, public_id)
        except PeerLookupError as exc:
            log.debug("hint lookup %s failed: %s", hint, exc)
            return None
        if answer is None:
            return None
        # Mitigate threat T2: the peer must sign its answer with the
        # very node id the hint claims to host the recipient on. A
        # directory client returning a different ack_node_id is
        # either buggy or adversarial; refuse the answer either way.
        pid, base_url, account_id, ack_node_id = answer
        if pid != public_id:
            log.warning("peer %s returned mismatched public id %r", hint, pid)
            return None
        if ack_node_id != hint:
            log.warning(
                "hint %s claimed by peer but signed by %s; refusing (T2)",
                hint,
                ack_node_id,
            )
            return None
        try:
            self._inner.add(public_id, base_url, account_id)
        except Exception:  # noqa: BLE001
            pass
        return base_url

    def _consult_peers(self, public_id: str) -> list[str]:
        """Ask every known peer; return all answers that pass T2 checks.

        Each answer's ``ack_node_id`` is verified against any
        ``node_id_hint`` embedded in the public id. Answers with no
        hint pass; answers where the hint does not match the signing
        node are dropped.
        """
        hint = decode_node_hint(public_id)
        results: list[str] = []
        for answer in self._peer.ask_all(public_id):
            if answer is None:
                continue
            pid, base_url, account_id, ack_node_id = answer
            if pid != public_id:
                continue
            if hint and ack_node_id != hint:
                log.warning(
                    "peer answer signed by %s but public id hints %s; dropping (T2)",
                    ack_node_id,
                    hint,
                )
                continue
            try:
                self._inner.add(public_id, base_url, account_id)
            except Exception:  # noqa: BLE001
                pass
            results.append(base_url)
        return results

    def lookup(self, public_id: str) -> Optional[str]:
        local = self._inner.lookup(public_id)
        if local is not None:
            return local
        hinted = self._consult_hint(public_id)
        if hinted is not None:
            return hinted
        answers = self._consult_peers(public_id)
        if answers:
            return answers[0]
        return None

    def add(self, public_id: str, base_url: str, account_id: str) -> None:
        self._inner.add(public_id, base_url, account_id)

    def remove(self, public_id: str) -> bool:
        return self._inner.remove(public_id)

    def all_entries(self) -> list[tuple[str, str, str]]:
        return self._inner.all_entries()


__all__ = [
    "CachingDirectory",
    "DistributedDirectory",
    "PeerLookupError",
]
