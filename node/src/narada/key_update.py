"""On-the-wire key rotation announcement (Phase 1 follow-up).

A ``NaradaKeyUpdate`` is a signed, sealed envelope that tells one
recipient "my old key is no longer my primary; please use this
new key going forward." It is structurally identical to a normal
envelope except:

* ``v = 3`` (a new envelope version; user identities remain V1/V2)
* the body is a regular :class:`NaradaBody` whose ``subject`` is
  the sentinel ``"__narada_key_update__"`` and whose ``body_text``
  is a JSON-serialised :class:`KeyUpdateBody`

The header is signed with the OLD key so the recipient can prove
the update came from the same owner as the prior identity. The
body is sealed to the recipient (X25519 ECDH + ChaCha20-Poly1305
as in regular envelopes) so a passive observer cannot read the
new public id.

KeyUpdateBody fields::

    prior_public_id   str   - the OLD narada1... identity
    new_public_id     str   - the NEW narada1... identity
    not_after         int   - unix seconds; until then, the OLD key
                             is still acceptable for new envelopes
    new_node_id_hint  str?  - optional V2 hint for the new identity
    issuer_node_id    str?  - optional node id that signed the update

Verification on receipt:

1. :func:`open_key_update_envelope` opens the envelope using the
   recipient's own seed. The header signature is verified against
   ``prior_public_id`` (which the recipient already has on file).
2. The recipient persists a (prior_public_id, new_public_id,
   not_after) tuple into a :class:`KeyRotationStore` so future
   envelopes signed under the OLD public id can be accepted
   during the overlap window.
"""

from __future__ import annotations

import base64
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from src.narada.envelope import (
    NaradaBody,
    NaradaEnvelope,
    NaradaEnvelopeError,
    _canonical_json,
    _hkdf_salt_for,
    open_envelope,
)
from src.narada_identity.encoding import decode_public_id
from src.narada_identity.identity import NaradaIdentity

KEY_UPDATE_ENVELOPE_VERSION = 3
_KEY_UPDATE_BODY_VERSION = 1

# Default overlap window during which the OLD key is still acceptable.
DEFAULT_OVERLAP_SECONDS = 7 * 24 * 60 * 60

# Sentinel subject for the NaradaBody inside a v=3 envelope.
KEY_UPDATE_SENTINEL_SUBJECT = "__narada_key_update__"


class KeyUpdateError(Exception):
    """Raised when a key update envelope cannot be parsed or verified."""


@dataclass(frozen=True)
class KeyUpdateBody:
    prior_public_id: str
    new_public_id: str
    not_after: int
    new_node_id_hint: Optional[str] = None
    issuer_node_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "prior_public_id": self.prior_public_id,
            "new_public_id": self.new_public_id,
            "not_after": self.not_after,
            "v": _KEY_UPDATE_BODY_VERSION,
        }
        if self.new_node_id_hint is not None:
            out["new_node_id_hint"] = self.new_node_id_hint
        if self.issuer_node_id is not None:
            out["issuer_node_id"] = self.issuer_node_id
        return out

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "KeyUpdateBody":
        try:
            v = int(data.get("v", 0))
        except (TypeError, ValueError) as exc:
            raise KeyUpdateError(f"bad key-update body version: {exc}") from exc
        if v != _KEY_UPDATE_BODY_VERSION:
            raise KeyUpdateError(f"unknown key-update body version: {v}")
        try:
            return cls(
                prior_public_id=str(data["prior_public_id"]),
                new_public_id=str(data["new_public_id"]),
                not_after=int(data["not_after"]),
                new_node_id_hint=(
                    str(data["new_node_id_hint"])
                    if data.get("new_node_id_hint") is not None
                    else None
                ),
                issuer_node_id=(
                    str(data["issuer_node_id"])
                    if data.get("issuer_node_id") is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise KeyUpdateError(
                f"missing or wrong-typed key-update field: {exc}"
            ) from exc


def _seal_envelope_with_version(
    sender_identity: NaradaIdentity,
    recipient_public_id: str,
    body_dict: Mapping[str, Any],
    *,
    version: int,
    timestamp: Optional[int] = None,
    message_id: Optional[str] = None,
    node=None,
) -> NaradaEnvelope:
    """Build a sealed envelope with a custom ``v`` byte.

    Mirrors :func:`src.narada.envelope.make_envelope` but lets the
    caller pin the wire version. Used for key-update envelopes
    (v=3); the regular make_envelope is hardcoded to v=1.
    """
    try:
        _ver, _ed_pub, recipient_x_pub = decode_public_id(recipient_public_id)
    except Exception as exc:
        raise KeyUpdateError(f"invalid recipient public id: {exc}") from exc

    mid = message_id if message_id else str(uuid.uuid4())
    ts = int(timestamp) if timestamp is not None else int(time.time())
    nonce = secrets.token_bytes(16)
    aead_nonce = nonce[:12]

    shared = sender_identity.keypair.shared_secret_with(recipient_x_pub)
    salt = _hkdf_salt_for(sender_identity.public_id, mid)
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"Narada-envelope-v1",
    ).derive(shared)

    body = NaradaBody(
        subject=KEY_UPDATE_SENTINEL_SUBJECT,
        body_text=json.dumps(dict(body_dict), separators=(",", ":")),
        to=(recipient_public_id,),
    )
    body_bytes = _canonical_json(body.to_dict())

    header_dict = {
        "v": int(version),
        "sender_public_id": sender_identity.public_id,
        "recipient_public_id": recipient_public_id,
        "message_id": mid,
        "timestamp": ts,
        "nonce": base64.b64encode(nonce).decode("ascii"),
    }
    header_bytes = _canonical_json(header_dict)
    ciphertext = ChaCha20Poly1305(key).encrypt(
        aead_nonce, body_bytes, associated_data=header_bytes
    )
    signature = sender_identity.keypair.sign(header_bytes)

    sender_node_id: Optional[str] = None
    sender_node_signature: Optional[bytes] = None
    if node is not None:
        sender_node_id = node.public_id
        node_payload = header_bytes + b"|" + sender_node_id.encode("ascii")
        sender_node_signature = node.sign(node_payload)

    return NaradaEnvelope(
        v=int(version),
        sender_public_id=sender_identity.public_id,
        recipient_public_id=recipient_public_id,
        message_id=mid,
        timestamp=ts,
        nonce=nonce,
        signature=signature,
        body_ciphertext=ciphertext,
        sender_node_id=sender_node_id,
        sender_node_signature=sender_node_signature,
    )


def make_key_update_envelope(
    sender_identity: NaradaIdentity,
    recipient_public_id: str,
    new_identity: NaradaIdentity,
    *,
    not_after: Optional[int] = None,
    issuer_node_id: Optional[str] = None,
    new_node_id_hint: Optional[str] = None,
    timestamp: Optional[int] = None,
    message_id: Optional[str] = None,
    node=None,
) -> NaradaEnvelope:
    """Build a sealed NaradaKeyUpdate envelope.

    ``sender_identity`` is the OLD identity; ``new_identity`` is the
    NEW identity the sender wants to start using. The envelope's
    header is signed with the OLD key so the recipient can verify
    the update came from the same owner as the prior identity.
    """
    if sender_identity.public_id == new_identity.public_id:
        raise KeyUpdateError("new identity has the same public_id as the prior")
    not_after_ts = int(not_after) if not_after is not None else int(
        time.time() + DEFAULT_OVERLAP_SECONDS
    )

    body = KeyUpdateBody(
        prior_public_id=sender_identity.public_id,
        new_public_id=new_identity.public_id,
        not_after=not_after_ts,
        issuer_node_id=issuer_node_id,
        new_node_id_hint=new_node_id_hint,
    ).to_dict()
    return _seal_envelope_with_version(
        sender_identity=sender_identity,
        recipient_public_id=recipient_public_id,
        body_dict=body,
        version=KEY_UPDATE_ENVELOPE_VERSION,
        timestamp=timestamp,
        message_id=message_id,
        node=node,
    )


def open_key_update_envelope(
    envelope: NaradaEnvelope,
    recipient_identity: NaradaIdentity,
    *,
    max_timestamp_skew_seconds: int = 5 * 60,
) -> KeyUpdateBody:
    """Decrypt a NaradaKeyUpdate envelope and return its body.

    Raises :class:`KeyUpdateError` on any failure.
    """
    if envelope.v != KEY_UPDATE_ENVELOPE_VERSION:
        raise KeyUpdateError(
            f"not a key-update envelope: version {envelope.v}"
        )
    try:
        body = open_envelope(
            envelope,
            recipient_identity,
            max_timestamp_skew_seconds=max_timestamp_skew_seconds,
        )
    except NaradaEnvelopeError as exc:
        raise KeyUpdateError(f"key-update envelope rejected: {exc}") from exc
    if body.subject != KEY_UPDATE_SENTINEL_SUBJECT:
        raise KeyUpdateError(
            "envelope subject is not the key-update sentinel"
        )
    try:
        body_dict = json.loads(body.body_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise KeyUpdateError(f"key-update body is not valid JSON: {exc}") from exc
    if not isinstance(body_dict, dict):
        raise KeyUpdateError("key-update body is not a JSON object")
    return KeyUpdateBody.from_dict(body_dict)


__all__ = [
    "DEFAULT_OVERLAP_SECONDS",
    "KEY_UPDATE_ENVELOPE_VERSION",
    "KEY_UPDATE_SENTINEL_SUBJECT",
    "KeyUpdateBody",
    "KeyUpdateError",
    "make_key_update_envelope",
    "open_key_update_envelope",
]