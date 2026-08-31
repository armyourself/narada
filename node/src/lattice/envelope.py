"""Lattice protocol envelope (Phase 2 MVP).

An envelope is a JSON object that wraps an encrypted + signed message.
See ``protocol/message-format.md`` for the full spec.

Crypto recipe (sign-then-encrypt, signature over canonical header):

  shared    = X25519(sender_static_priv, recipient_x25519_pub)
  key       = HKDF-SHA256(shared, salt=SHA256(sender_pub || ":" || message_id),
                                    info=b"lattice-envelope-v1",
                                    length=32)
  nonce     = 16 random bytes  (we use the first 12 for ChaCha20-Poly1305)
  aad       = canonical_header_bytes
  body_ct   = ChaCha20-Poly1305(key, nonce=nonce[:12], plaintext=body, aad=aad)
  signature = Ed25519(sender_ed25519_priv, canonical_header_bytes)

The signature is computed *before* encryption, over the canonical header
(no signature, no body_ciphertext, no body_plaintext). The recipient
verifies the signature first, then decrypts. This means a malformed or
untrusted envelope is rejected before any AEAD work happens.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from src.lattice_identity.encoding import decode_public_id
from src.lattice_identity.errors import LatticeIdentityError
from src.lattice_identity.identity import LatticeIdentity, verify_public_id_signature


# --- Constants -------------------------------------------------------------

ENVELOPE_VERSION = 1
_ENVELOPE_HKDF_INFO = b"lattice-envelope-v1"
_NONCE_LEN = 16  # 128 bits; we use the first 12 for ChaCha20-Poly1305.
                  # Random per message -> collision risk negligible.

# Public field names. Used both for canonical JSON ordering and for input
# validation; this is the wire format.
_FIELDS = (
    "v",
    "sender_public_id",
    "recipient_public_id",
    "message_id",
    "timestamp",
    "nonce",
    "signature",
    "body_ciphertext",
)


# --- Errors -----------------------------------------------------------------


class LatticeEnvelopeError(LatticeIdentityError):
    """Raised by envelope seal/open operations."""


# --- Body -------------------------------------------------------------------


@dataclass(frozen=True)
class LatticeBody:
    """The plaintext payload of a Lattice message (recipient-visible)."""

    subject: str = ""
    sender: str = ""  # display name + address, e.g. "Alice <alice@example.com>"
    to: tuple[str, ...] = ()
    cc: tuple[str, ...] = ()
    body_text: str = ""
    sent_at: int = 0  # unix seconds (0 = "not set")

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "sender": self.sender,
            "to": list(self.to),
            "cc": list(self.cc),
            "body_text": self.body_text,
            "sent_at": self.sent_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LatticeBody":
        return cls(
            subject=str(data.get("subject", "")),
            sender=str(data.get("sender", "")),
            to=tuple(str(t) for t in data.get("to", []) or ()),
            cc=tuple(str(c) for c in data.get("cc", []) or ()),
            body_text=str(data.get("body_text", "")),
            sent_at=int(data.get("sent_at", 0) or 0),
        )


# --- Envelope ---------------------------------------------------------------


@dataclass(frozen=True)
class LatticeEnvelope:
    """A sealed Lattice message.

    The transport layer ships the ``as_dict()`` form (JSON).
    """

    v: int
    sender_public_id: str
    recipient_public_id: str
    message_id: str
    timestamp: int
    nonce: bytes
    signature: bytes
    body_ciphertext: bytes

    def as_dict(self) -> dict[str, Any]:
        return {
            "v": self.v,
            "sender_public_id": self.sender_public_id,
            "recipient_public_id": self.recipient_public_id,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "nonce": base64.b64encode(self.nonce).decode("ascii"),
            "signature": base64.b64encode(self.signature).decode("ascii"),
            "body_ciphertext": base64.b64encode(self.body_ciphertext).decode("ascii"),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LatticeEnvelope":
        if not isinstance(data, Mapping):
            raise LatticeEnvelopeError("envelope must be a JSON object")
        try:
            nonce_b64 = data["nonce"]
            sig_b64 = data["signature"]
            ct_b64 = data["body_ciphertext"]
        except KeyError as exc:
            raise LatticeEnvelopeError(f"envelope missing field: {exc.args[0]}") from exc
        try:
            return cls(
                v=int(data["v"]),
                sender_public_id=str(data["sender_public_id"]),
                recipient_public_id=str(data["recipient_public_id"]),
                message_id=str(data["message_id"]),
                timestamp=int(data["timestamp"]),
                nonce=base64.b64decode(nonce_b64, validate=True),
                signature=base64.b64decode(sig_b64, validate=True),
                body_ciphertext=base64.b64decode(ct_b64, validate=True),
            )
        except (TypeError, ValueError, base64.binascii.Error) as exc:
            raise LatticeEnvelopeError(f"envelope field has wrong type/encoding: {exc}") from exc


# --- Canonical JSON (stable across runs and platforms) ----------------------


def _canonical_json(mapping: Mapping[str, Any]) -> bytes:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8.

    Used both for the bytes the signature covers and the AAD passed to
    the AEAD. Both ends must use the same encoding or signature/AAD
    checks will fail.
    """
    return json.dumps(
        mapping,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


# --- Header (envelope without signature or ciphertext) ----------------------


def _header_bytes(env: LatticeEnvelope) -> bytes:
    """Canonical bytes of the header — what the signature covers and the AEAD AAD."""
    return _canonical_json(
        {
            "v": env.v,
            "sender_public_id": env.sender_public_id,
            "recipient_public_id": env.recipient_public_id,
            "message_id": env.message_id,
            "timestamp": env.timestamp,
            "nonce": base64.b64encode(env.nonce).decode("ascii"),
        }
    )


# --- Helpers ----------------------------------------------------------------


def _hkdf_salt_for(sender_public_id: str, message_id: str) -> bytes:
    """Salt = SHA-256(sender_public_id || ":" || message_id).

    Binds the AEAD key to (sender, message_id) so a single (sender,
    recipient) pair never reuses the same AEAD key across distinct
    messages. 32 bytes.
    """
    return hashlib.sha256(f"{sender_public_id}:{message_id}".encode("utf-8")).digest()


# --- Seal / open ------------------------------------------------------------


def make_envelope(
    sender: LatticeIdentity,
    recipient_public_id: str,
    body: LatticeBody,
    *,
    timestamp: int | None = None,
    message_id: str | None = None,
) -> LatticeEnvelope:
    """Build a sealed Lattice envelope from plaintext ``body``.

    The caller is expected to ship ``envelope.as_dict()`` to the
    recipient (over a :class:`LatticeTransport`).
    """
    try:
        _version, _ed_pub, recipient_x_pub = decode_public_id(recipient_public_id)
    except Exception as exc:
        raise LatticeEnvelopeError(f"invalid recipient public id: {exc}") from exc

    mid = message_id if message_id else str(uuid.uuid4())
    ts = int(timestamp) if timestamp is not None else int(time.time())
    nonce = secrets.token_bytes(_NONCE_LEN)
    aead_nonce = nonce[:12]  # ChaCha20-Poly1305 takes a 12-byte nonce.

    shared = sender.keypair.shared_secret_with(recipient_x_pub)
    salt = _hkdf_salt_for(sender.public_id, mid)
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=_ENVELOPE_HKDF_INFO,
    ).derive(shared)

    body_bytes = _canonical_json(body.to_dict())

    # Build the header first so we can sign + encrypt against it.
    header_dict = {
        "v": ENVELOPE_VERSION,
        "sender_public_id": sender.public_id,
        "recipient_public_id": recipient_public_id,
        "message_id": mid,
        "timestamp": ts,
        "nonce": base64.b64encode(nonce).decode("ascii"),
    }
    header_bytes = _canonical_json(header_dict)

    aead = ChaCha20Poly1305(key)
    body_ciphertext = aead.encrypt(aead_nonce, body_bytes, associated_data=header_bytes)

    signature = sender.keypair.sign(header_bytes)

    return LatticeEnvelope(
        v=ENVELOPE_VERSION,
        sender_public_id=sender.public_id,
        recipient_public_id=recipient_public_id,
        message_id=mid,
        timestamp=ts,
        nonce=nonce,
        signature=signature,
        body_ciphertext=body_ciphertext,
    )


def open_envelope(
    envelope: LatticeEnvelope,
    recipient: LatticeIdentity,
    *,
    max_timestamp_skew_seconds: int = 5 * 60,
    now: int | None = None,
) -> LatticeBody:
    """Verify, decrypt, and return the body of ``envelope``.

    Steps:
      1. Recipient public id matches our identity.
      2. Envelope version is supported.
      3. Timestamp is within ``max_timestamp_skew_seconds`` of ``now``.
      4. Ed25519 signature is valid for the canonical header.
      5. ChaCha20-Poly1305 decrypts the body with AAD = header bytes.

    Any failure raises :class:`LatticeEnvelopeError` with a stable
    message; the caller (router) maps it to a 4xx.
    """
    if envelope.recipient_public_id != recipient.public_id:
        raise LatticeEnvelopeError("envelope addressed to a different recipient")
    if envelope.v != ENVELOPE_VERSION:
        raise LatticeEnvelopeError(f"unsupported envelope version: {envelope.v}")

    current = int(now) if now is not None else int(time.time())
    if abs(current - envelope.timestamp) > max_timestamp_skew_seconds:
        raise LatticeEnvelopeError(
            f"envelope timestamp out of window: {envelope.timestamp} vs {current}"
        )

    # 1. Verify signature.
    header_bytes = _header_bytes(envelope)
    try:
        sig_ok = verify_public_id_signature(
            envelope.sender_public_id, envelope.signature, header_bytes
        )
    except LatticeIdentityError as exc:
        # Sender public id is malformed; treat as a signature failure
        # so the caller gets a single typed error.
        raise LatticeEnvelopeError(f"invalid sender public id: {exc}") from exc
    if not sig_ok:
        raise LatticeEnvelopeError("envelope signature is invalid")

    # 2. Decrypt.
    try:
        _version, _ed_pub, sender_x_pub = decode_public_id(envelope.sender_public_id)
    except Exception as exc:
        raise LatticeEnvelopeError(f"invalid sender public id: {exc}") from exc

    shared = recipient.keypair.shared_secret_with(sender_x_pub)
    salt = _hkdf_salt_for(envelope.sender_public_id, envelope.message_id)
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=_ENVELOPE_HKDF_INFO,
    ).derive(shared)

    aead = ChaCha20Poly1305(key)
    aead_nonce = envelope.nonce[:12]
    try:
        body_bytes = aead.decrypt(
            aead_nonce, envelope.body_ciphertext, associated_data=header_bytes
        )
    except (InvalidSignature, InvalidTag) as exc:
        raise LatticeEnvelopeError("envelope ciphertext is invalid or tampered") from exc

    try:
        body_dict = json.loads(body_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LatticeEnvelopeError("envelope body is not valid JSON") from exc

    if not isinstance(body_dict, dict):
        raise LatticeEnvelopeError("envelope body is not a JSON object")
    return LatticeBody.from_dict(body_dict)


__all__ = [
    "ENVELOPE_VERSION",
    "LatticeBody",
    "LatticeEnvelope",
    "LatticeEnvelopeError",
    "make_envelope",
    "open_envelope",
]

