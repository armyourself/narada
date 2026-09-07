"""FastAPI routes for the Narada relay (Phase 4).

The QUIC listener in ``node/src/narada/p2p/listener.py`` is the
production seam for ``relay.deposit`` / ``relay.fetch`` /
``relay.drop`` frames. The HTTP routes in this file give the same
surface over loopback HTTP for:

* desktop clients that want to push deposits / pull fetches
  directly without speaking QUIC;
* tests and smoke scripts;
* interop with pre-R4 nodes that already speak HTTP.

Wire compatibility: the request body is the same JSON the QUIC
handlers expect (``{type, v, ...}``), and the response is the same
JSON the QUIC handlers return. The HTTP routes share the
:class:`RelayStore` and node identity with the QUIC listener.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from src.narada.node_identity import (
    NaradaNodeIdentity,
    load_or_create,
)
from src.narada.relay import (
    RelayStore,
    RelayStoreError,
    make_stored_receipt,
)


router = APIRouter(tags=["Narada Relay"])


_RECIPIENT_PATTERN = re.compile(r"^[a-z0-9]{6,16}1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]+$")
_ACCOUNT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._@+\-]{1,254}$")


# Process-wide relay store; built lazily by :func:`get_relay_store`.
_store: Optional[RelayStore] = None
_node_identity: Optional[NaradaNodeIdentity] = None
_data_dir: Optional[Path] = None
_master_key: Optional[bytes] = None


def configure(
    *,
    data_dir: Path,
    master_key: bytes,
    node_identity: Optional[NaradaNodeIdentity] = None,
) -> RelayStore:
    """Initialise (or replace) the singleton relay store.

    Called from :mod:`src.main` during the FastAPI lifespan. Tests
    can call this directly with a tmp directory.
    """
    global _store, _node_identity, _data_dir, _master_key
    _data_dir = Path(data_dir)
    _master_key = bytes(master_key[:32])
    if node_identity is None:
        node_identity = load_or_create(_data_dir)
    _node_identity = node_identity
    _store = RelayStore(_data_dir, master_key=_master_key)
    return _store


def reset_for_tests() -> None:
    global _store, _node_identity, _data_dir, _master_key
    _store = None
    _node_identity = None
    _data_dir = None
    _master_key = None


def get_relay_store() -> RelayStore:
    if _store is None:
        raise RelayStoreError(
            "relay store not initialised; call configure() first"
        )
    return _store


def get_node_identity() -> NaradaNodeIdentity:
    if _node_identity is None:
        raise RelayStoreError(
            "relay node identity not initialised; call configure() first"
        )
    return _node_identity


def _validate_recipient(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not _RECIPIENT_PATTERN.match(value):
        return None
    return value


# --- deposit ----------------------------------------------------------------


class DepositRequest(BaseModel):
    v: int = 1
    envelope: Mapping[str, Any]
    expires_at: Optional[int] = None


@router.post("/narada/relay/deposit")
async def deposit(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        return {"type": "error", "message": "request body must be JSON"}
    if not isinstance(body, Mapping):
        return {"type": "error", "message": "body must be a JSON object"}
    envelope = body.get("envelope")
    if not isinstance(envelope, Mapping):
        return {"type": "error", "message": "envelope must be a JSON object"}
    recipient = _validate_recipient(envelope.get("recipient_public_id"))
    sender = envelope.get("sender_public_id")
    if recipient is None or not isinstance(sender, str):
        return {"type": "error", "message": "envelope sender/recipient invalid"}
    if int(body.get("v", 1)) != 1:
        return {"type": "error", "message": "unsupported relay frame version"}
    store = get_relay_store()
    node = get_node_identity()
    try:
        stored = store.deposit(
            sender_public_id=str(sender),
            envelope=envelope,
            recipient_public_id=recipient,
        )
    except RelayStoreError as exc:
        return {"type": "error", "message": str(exc)}
    receipt = make_stored_receipt(
        relay=node,
        deposit_id=stored.deposit_id,
        recipient_public_id=stored.recipient_public_id,
        message_id=str(envelope.get("message_id", "")),
        stored_at=stored.stored_at,
        expires_at=stored.expires_at,
    )
    return receipt.as_dict()


# --- fetch ------------------------------------------------------------------


class FetchRequest(BaseModel):
    v: int = 1
    recipient_public_id: str
    limit: int = 64


@router.post("/narada/relay/fetch")
async def fetch(request: FetchRequest) -> dict:
    recipient = _validate_recipient(request.recipient_public_id)
    if recipient is None:
        return {"type": "error", "message": "recipient_public_id invalid"}
    if request.v != 1:
        return {"type": "error", "message": "unsupported relay frame version"}
    limit = max(0, min(request.limit, 256))
    store = get_relay_store()
    deposits = store.fetch(recipient_public_id=recipient, limit=limit)
    return {
        "type": "relay.fetch.result",
        "deposits": [
            {
                "deposit_id": d.deposit_id,
                "recipient_public_id": d.recipient_public_id,
                "envelope": d.envelope,
                "stored_at": d.stored_at,
                "expires_at": d.expires_at,
                "size_bytes": d.size_bytes,
            }
            for d in deposits
        ],
    }


# --- drop -------------------------------------------------------------------


class DropRequest(BaseModel):
    v: int = 1
    recipient_public_id: str
    deposit_ids: list[str]


@router.post("/narada/relay/drop")
async def drop(request: DropRequest) -> dict:
    recipient = _validate_recipient(request.recipient_public_id)
    if recipient is None:
        return {"type": "error", "message": "recipient_public_id invalid"}
    if request.v != 1:
        return {"type": "error", "message": "unsupported relay frame version"}
    if not all(isinstance(i, str) for i in request.deposit_ids):
        return {"type": "error", "message": "deposit_ids must be a list of strings"}
    store = get_relay_store()
    removed = store.drop(
        recipient_public_id=recipient, deposit_ids=request.deposit_ids
    )
    return {"type": "relay.drop.result", "removed": int(removed)}


# --- sweep (admin) ----------------------------------------------------------


@router.post("/narada/relay/sweep")
async def sweep() -> dict:
    store = get_relay_store()
    removed = store.sweep()
    return {"type": "relay.sweep.result", "removed": int(removed)}


__all__ = [
    "router",
    "configure",
    "reset_for_tests",
    "get_relay_store",
    "get_node_identity",
]
