"""In-process relay transport for tests.

Tests need to exercise the relay path without spinning up aioquic.
This module exposes an in-memory client/registry that ships
``relay.*`` frames directly to a :class:`HandlerRegistry` and
returns the handler's reply, bypassing the QUIC layer.
"""

from __future__ import annotations

import threading
from typing import Optional

from src.narada.p2p.listener import HandlerRegistry

from .handlers import build_deposit_handler, build_drop_handler, build_fetch_handler
from .receipt import StoredReceipt
from .store import RelayStore, RelayStoreError
from src.narada.node_identity import NaradaNodeIdentity


class InProcessRelay:
    """Wire a :class:`RelayStore` to a :class:`HandlerRegistry` and
    expose a synchronous client that hits it in-process.

    Use ``InProcessRelay.as_client()`` to obtain a client that
    dispatches to this registry; tests can then drop aioquic and
    run everything in one event loop or thread.
    """

    def __init__(
        self,
        *,
        data_dir,
        master_key: bytes,
        relay_identity: NaradaNodeIdentity,
    ) -> None:
        self.store = RelayStore(data_dir, master_key=master_key)
        self.relay_identity = relay_identity
        self.registry = HandlerRegistry()
        self.registry.register("relay.deposit", build_deposit_handler(
            store=self.store, relay_identity=self.relay_identity
        ))
        self.registry.register("relay.fetch", build_fetch_handler(store=self.store))
        self.registry.register("relay.drop", build_drop_handler(store=self.store))
        self._lock = threading.RLock()

    def deposit(self, payload: dict) -> dict:
        with self._lock:
            return self.registry.dispatch(
                {"type": "relay.deposit", **payload}, ("test", 0)
            )

    def fetch(self, payload: dict) -> dict:
        with self._lock:
            return self.registry.dispatch(
                {"type": "relay.fetch", **payload}, ("test", 0)
            )

    def drop(self, payload: dict) -> dict:
        with self._lock:
            return self.registry.dispatch(
                {"type": "relay.drop", **payload}, ("test", 0)
            )


__all__ = ["InProcessRelay"]
