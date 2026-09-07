"""QUIC listener handlers for the Narada relay (Phase 4).

Three frame types ride on the existing
:class:`src.narada.p2p.listener.HandlerRegistry`:

* ``relay.deposit`` -- sender asks the relay to hold an envelope
* ``relay.fetch``   -- recipient asks for envelopes addressed to it
* ``relay.drop``    -- recipient asks the relay to delete picked-up
                       envelopes

All three share the same validation surface (account_id-style
recipient id, signed envelope, sensible defaults) and return a JSON
object with a ``type`` field that matches the request's prefix.

Receipts are returned as ``relay.stored`` frames; see
:mod:`.receipt`.
"""

from __future__ import annotations

from typing import Callable, Mapping, Optional

from src.narada.node_identity import NaradaNodeIdentity

from .receipt import make_stored_receipt
from .store import RelayBadDeposit, RelayQuotaExceeded, RelayStore, StoredDeposit


_RELAY_VERSION = 1


def _error(message: str) -> dict:
    return {"type": "error", "message": message}


# --- build_deposit_handler -----------------------------------------------


def build_deposit_handler(
    *,
    store: RelayStore,
    relay_identity: NaradaNodeIdentity,
):
    """Return a handler that accepts ``relay.deposit`` frames.

    The handler:

    * Validates the frame shape.
    * Calls :meth:`RelayStore.deposit`.
    * Returns ``{"type": "relay.stored", ...}`` with a signed receipt
      on success, ``{"type": "error", ...}`` on failure.
    """

    def handler(payload: dict, peer_addr: tuple[str, int]) -> dict:
        if not isinstance(payload, Mapping):
            return _error("payload must be a JSON object")
        v = payload.get("v")
        if v != _RELAY_VERSION:
            return _error(f"unsupported relay frame version: {v!r}")
        envelope = payload.get("envelope")
        if not isinstance(envelope, Mapping):
            return _error("envelope must be a JSON object")
        try:
            sender_public_id = str(envelope["sender_public_id"])
            recipient_public_id = str(envelope["recipient_public_id"])
        except KeyError:
            return _error("envelope missing sender_public_id or recipient_public_id")
        ttl = payload.get("expires_at")
        try:
            stored = store.deposit(
                sender_public_id=sender_public_id,
                envelope=envelope,
                recipient_public_id=recipient_public_id,
                ttl_seconds=_ttl_from_expires_at(
                    ttl, sender_payload=payload
                ),
            )
        except RelayQuotaExceeded as exc:
            return {
                "type": "relay.deposit.error",
                "code": "quota_exceeded",
                "message": str(exc),
            }
        except RelayBadDeposit as exc:
            return {
                "type": "relay.deposit.error",
                "code": "bad_deposit",
                "message": str(exc),
            }
        receipt = make_stored_receipt(
            relay=relay_identity,
            deposit_id=stored.deposit_id,
            recipient_public_id=stored.recipient_public_id,
            message_id=str(envelope.get("message_id", "")),
            stored_at=stored.stored_at,
            expires_at=stored.expires_at,
        )
        return receipt.as_dict()

    return handler


def _ttl_from_expires_at(value, *, sender_payload: Mapping) -> Optional[int]:
    """Translate the optional ``expires_at`` field into a TTL.

    The sender can either pin ``expires_at`` (absolute unix seconds)
    or omit it (the relay uses its default). The store takes a
    ``ttl_seconds`` parameter; we resolve the delta here.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        import time

        delta = int(value) - int(time.time())
        if delta <= 0:
            return 1
        return delta
    return None


# --- build_fetch_handler --------------------------------------------------


def build_fetch_handler(*, store: RelayStore):
    """Return a handler for ``relay.fetch`` requests.

    The handler returns ``{"type": "relay.fetch.result", "deposits": [...]}``
    on success. The deposits are returned **without** any envelope
    mutation; the recipient opens them locally with its own
    identity.
    """

    def handler(payload: dict, peer_addr: tuple[str, int]) -> dict:
        if not isinstance(payload, Mapping):
            return _error("payload must be a JSON object")
        if payload.get("v") != _RELAY_VERSION:
            return _error(
                f"unsupported relay frame version: {payload.get('v')!r}"
            )
        recipient = payload.get("recipient_public_id")
        if not isinstance(recipient, str) or not recipient:
            return _error("recipient_public_id must be a non-empty string")
        try:
            limit = int(payload.get("limit", 64))
        except (TypeError, ValueError):
            return _error("limit must be an integer")
        limit = max(0, min(limit, 256))
        try:
            deposits = store.fetch(
                recipient_public_id=recipient, limit=limit
            )
        except RelayBadDeposit as exc:
            return _error(str(exc))
        return {
            "type": "relay.fetch.result",
            "deposits": [_deposit_to_dict(d) for d in deposits],
        }

    return handler


def _deposit_to_dict(d: StoredDeposit) -> dict:
    return {
        "deposit_id": d.deposit_id,
        "recipient_public_id": d.recipient_public_id,
        "envelope": d.envelope,
        "stored_at": d.stored_at,
        "expires_at": d.expires_at,
        "size_bytes": d.size_bytes,
    }


# --- build_drop_handler ---------------------------------------------------


def build_drop_handler(*, store: RelayStore):
    """Return a handler for ``relay.drop`` requests.

    Only the owning recipient can drop its deposits; mismatched
    recipient_public_id values are silently ignored.
    """

    def handler(payload: dict, peer_addr: tuple[str, int]) -> dict:
        if not isinstance(payload, Mapping):
            return _error("payload must be a JSON object")
        if payload.get("v") != _RELAY_VERSION:
            return _error(
                f"unsupported relay frame version: {payload.get('v')!r}"
            )
        recipient = payload.get("recipient_public_id")
        ids = payload.get("deposit_ids")
        if not isinstance(recipient, str) or not recipient:
            return _error("recipient_public_id must be a non-empty string")
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            return _error("deposit_ids must be a list of strings")
        try:
            removed = store.drop(recipient_public_id=recipient, deposit_ids=ids)
        except RelayBadDeposit as exc:
            return _error(str(exc))
        return {"type": "relay.drop.result", "removed": int(removed)}

    return handler


def register_relay_handlers(
    *,
    registry,
    store: RelayStore,
    relay_identity: NaradaNodeIdentity,
) -> None:
    """Register deposit / fetch / drop on a :class:`HandlerRegistry`."""
    registry.register("relay.deposit", build_deposit_handler(
        store=store, relay_identity=relay_identity
    ))
    registry.register("relay.fetch", build_fetch_handler(store=store))
    registry.register("relay.drop", build_drop_handler(store=store))


__all__ = [
    "build_deposit_handler",
    "build_drop_handler",
    "build_fetch_handler",
    "register_relay_handlers",
]
