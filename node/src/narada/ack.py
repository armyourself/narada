"""Delivery acknowledgements for the Narada protocol (Phase 2 wiring).

When a recipient's node successfully persists an incoming envelope,
it returns a signed :class:`NaradaAck` to the sender. The ack is
cryptographically bound to the original envelope (via ``message_id`` +
``sender_public_id`` + ``recipient_public_id``), so:

* the sender can be sure a delivery they attribute to ``recipient_public_id``
  was confirmed by that recipient's node identity;
* the sender's outbox entry can transition from "queued/sent" to "acked";
* a malicious or compromised node cannot ack on behalf of a recipient
  whose node key it does not hold.

The ack is intentionally minimal: a single ``status`` field plus the
three identifiers needed to bind the ack to one envelope. Everything
else lives in the original envelope.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from src.narada.node_identity import NaradaNodeIdentity, verify_node_signature

ACK_STATUS_DELIVERED = "delivered"
ACK_STATUS_REJECTED = "rejected"  # Reserved for future use.


class NaradaAckError(Exception):
    """Raised when an ack cannot be parsed, signed, or verified."""


@dataclass(frozen=True)
class NaradaAck:
    """A signed delivery acknowledgement for a single envelope."""

    v: int
    sender_public_id: str  # who sent the original envelope
    recipient_public_id: str  # who received it (acked-on-behalf-of)
    message_id: str
    timestamp: int  # when the recipient accepted it
    status: str  # one of ACK_STATUS_*
    node_id: str  # recipient node's public id
    signature: bytes

    def as_dict(self) -> dict[str, Any]:
        import base64

        return {
            "v": self.v,
            "sender_public_id": self.sender_public_id,
            "recipient_public_id": self.recipient_public_id,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "status": self.status,
            "node_id": self.node_id,
            "signature": base64.b64encode(self.signature).decode("ascii"),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NaradaAck":
        import base64

        if not isinstance(data, Mapping):
            raise NaradaAckError("ack must be a JSON object")
        try:
            sig_b64 = data["signature"]
        except KeyError as exc:
            raise NaradaAckError(f"ack missing field: {exc.args[0]}") from exc
        try:
            return cls(
                v=int(data["v"]),
                sender_public_id=str(data["sender_public_id"]),
                recipient_public_id=str(data["recipient_public_id"]),
                message_id=str(data["message_id"]),
                timestamp=int(data["timestamp"]),
                status=str(data["status"]),
                node_id=str(data["node_id"]),
                signature=base64.b64decode(sig_b64, validate=True),
            )
        except (TypeError, ValueError, base64.binascii.Error) as exc:
            raise NaradaAckError(f"ack field has wrong type/encoding: {exc}") from exc


ACK_VERSION = 1


def _canonical_payload(
    sender_public_id: str,
    recipient_public_id: str,
    message_id: str,
    timestamp: int,
    status: str,
) -> bytes:
    """Deterministic bytes the recipient node signs.

    Field order is fixed; the version byte is included so a future
    ack-version bump does not collide with old signatures.
    """
    parts = (
        bytes([ACK_VERSION]),
        sender_public_id.encode("utf-8"),
        recipient_public_id.encode("utf-8"),
        message_id.encode("utf-8"),
        b"%d" % int(timestamp),
        status.encode("utf-8"),
    )
    return b"|".join(parts)


def make_ack(
    node: NaradaNodeIdentity,
    sender_public_id: str,
    recipient_public_id: str,
    message_id: str,
    *,
    status: str = ACK_STATUS_DELIVERED,
    timestamp: Optional[int] = None,
) -> NaradaAck:
    """Build an ack signed by ``node`` for the given envelope."""
    if status not in (ACK_STATUS_DELIVERED, ACK_STATUS_REJECTED):
        raise NaradaAckError(f"unknown ack status: {status!r}")
    ts = int(timestamp) if timestamp is not None else int(time.time())
    payload = _canonical_payload(
        sender_public_id, recipient_public_id, message_id, ts, status
    )
    sig = node.sign(payload)
    return NaradaAck(
        v=ACK_VERSION,
        sender_public_id=sender_public_id,
        recipient_public_id=recipient_public_id,
        message_id=message_id,
        timestamp=ts,
        status=status,
        node_id=node.public_id,
        signature=sig,
    )


def verify_ack(
    ack: NaradaAck,
    *,
    expected_sender_public_id: str,
    expected_recipient_public_id: str,
    expected_message_id: str,
) -> bool:
    """Verify that ``ack`` is signed by the recipient's node and binds
    it to the expected envelope. Never raises.
    """
    if ack.v != ACK_VERSION:
        return False
    if ack.sender_public_id != expected_sender_public_id:
        return False
    if ack.recipient_public_id != expected_recipient_public_id:
        return False
    if ack.message_id != expected_message_id:
        return False
    payload = _canonical_payload(
        ack.sender_public_id,
        ack.recipient_public_id,
        ack.message_id,
        ack.timestamp,
        ack.status,
    )
    return verify_node_signature(ack.node_id, ack.signature, payload)


__all__ = [
    "ACK_STATUS_DELIVERED",
    "ACK_STATUS_REJECTED",
    "ACK_VERSION",
    "NaradaAck",
    "NaradaAckError",
    "make_ack",
    "verify_ack",
]