"""Signed ``relay.stored`` receipts (Phase 4).

The relay returns a small receipt to the sender after a successful
deposit so the sender can prove the relay accepted the envelope.
The receipt is signed by the **relay's** node identity (Ed25519),
not the recipient's, because the relay is the one asserting "I
have it". It is best-effort: a missing receipt does not invalidate
delivery (the recipient's ``NaradaAck`` is the source of truth).

Wire shape::

    {
      "type": "relay.stored",
      "v": 1,
      "deposit_id": "<uuid>",
      "recipient_public_id": "narada1...",
      "message_id": "<uuid>",
      "stored_at": 1735689700,
      "expires_at": 1736000000,
      "relay_node_id": "node1...",
      "signature": "<64 bytes, base64>"
    }

The signature covers the canonical JSON of the receipt without the
``signature`` field. See :doc:`/protocol/relay` for the rationale.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from src.narada.node_identity import (
    NaradaNodeIdentity,
    verify_node_signature,
)


RECEIPT_VERSION = 1


@dataclass(frozen=True)
class StoredReceipt:
    """A signed ``relay.stored`` receipt."""

    deposit_id: str
    recipient_public_id: str
    message_id: str
    stored_at: int
    expires_at: int
    relay_node_id: str
    signature: bytes

    def as_dict(self) -> dict:
        return {
            "type": "relay.stored",
            "v": RECEIPT_VERSION,
            "deposit_id": self.deposit_id,
            "recipient_public_id": self.recipient_public_id,
            "message_id": self.message_id,
            "stored_at": int(self.stored_at),
            "expires_at": int(self.expires_at),
            "relay_node_id": self.relay_node_id,
            "signature": base64.b64encode(self.signature).decode("ascii"),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StoredReceipt":
        if not isinstance(payload, Mapping):
            raise ValueError("receipt must be a JSON object")
        try:
            sig_b64 = payload["signature"]
            signature = base64.b64decode(sig_b64)
        except (KeyError, ValueError) as exc:
            raise ValueError("receipt has invalid signature encoding") from exc
        return cls(
            deposit_id=str(payload["deposit_id"]),
            recipient_public_id=str(payload["recipient_public_id"]),
            message_id=str(payload["message_id"]),
            stored_at=int(payload["stored_at"]),
            expires_at=int(payload["expires_at"]),
            relay_node_id=str(payload["relay_node_id"]),
            signature=signature,
        )


def _canonical_payload(receipt: StoredReceipt) -> bytes:
    """Deterministic JSON the relay signs. Excludes ``signature``."""
    payload = {
        "v": RECEIPT_VERSION,
        "deposit_id": receipt.deposit_id,
        "recipient_public_id": receipt.recipient_public_id,
        "message_id": receipt.message_id,
        "stored_at": int(receipt.stored_at),
        "expires_at": int(receipt.expires_at),
        "relay_node_id": receipt.relay_node_id,
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def make_stored_receipt(
    *,
    relay: NaradaNodeIdentity,
    deposit_id: str,
    recipient_public_id: str,
    message_id: str,
    stored_at: int,
    expires_at: int,
) -> StoredReceipt:
    """Build a receipt signed by the relay's node identity."""
    body = StoredReceipt(
        deposit_id=deposit_id,
        recipient_public_id=recipient_public_id,
        message_id=message_id,
        stored_at=int(stored_at),
        expires_at=int(expires_at),
        relay_node_id=relay.public_id,
        signature=b"",
    )
    signature = relay.sign(_canonical_payload(body))
    return StoredReceipt(
        deposit_id=body.deposit_id,
        recipient_public_id=body.recipient_public_id,
        message_id=body.message_id,
        stored_at=body.stored_at,
        expires_at=body.expires_at,
        relay_node_id=body.relay_node_id,
        signature=signature,
    )


def verify_stored_receipt(
    receipt: StoredReceipt, *, expected_message_id: Optional[str] = None
) -> bool:
    """Verify the relay signature. Optionally pin the message_id."""
    if expected_message_id is not None and receipt.message_id != expected_message_id:
        return False
    return verify_node_signature(
        receipt.relay_node_id, receipt.signature, _canonical_payload(receipt)
    )


__all__ = [
    "RECEIPT_VERSION",
    "StoredReceipt",
    "make_stored_receipt",
    "verify_stored_receipt",
]
