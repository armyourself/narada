"""Nostr-compatible identity layer.

A Nostr identity is an Ed25519 keypair. The public key is a 32-byte
hex string (the "npub" in NIP-19 bech32 form).

NIP-01: Keys are 32-byte hex strings.
NIP-19: Human-readable bech32 encoding (npub..., nsec...).

This module provides:

* :class:`NostrIdentity` -- a loaded identity with sign/verify
* :func:`generate_nostr_identity` -- create a new identity
* :func:`nostr_identity_from_seed` -- derive from an existing Ed25519 seed
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


# --- NIP-19 bech32 encoding ------------------------------------------------

_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32M_CONST = 0x2BC830A3


def _bech32m_polymod(values: list[int]) -> int:
    """Internal function that computes the Bech32m polymod."""
    GEN = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= GEN[i] if ((b >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _bech32m_verify_checksum(hrp: str, data: list[int]) -> bool:
    return _bech32m_polymod(_bech32_hrp_expand(hrp) + data) == _BECH32M_CONST


def _bech32m_create_checksum(hrp: str, data: list[int]) -> list[int]:
    values = _bech32_hrp_expand(hrp) + data
    polymod = _bech32m_polymod(values + [0] * 6) ^ _BECH32M_CONST
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def _convertbits(data: list[int], frombits: int, tobits: int, pad: bool = True) -> list[int]:
    """General power-of-2 base conversion."""
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            raise ValueError(f"Invalid value {value}")
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits:
        raise ValueError("Non-zero padding")
    elif (acc << (tobits - bits)) & maxv:
        raise ValueError("Non-zero padding")
    return ret


def bech32_encode(hrp: str, witver: int, witprog: list[int]) -> str:
    """Encode a bech32m string (NIP-19 uses witness version 0)."""
    data = _convertbits(witprog, 8, 5)
    combined = [witver] + data + _bech32m_create_checksum(hrp, [witver] + data)
    return hrp + "1" + "".join(_BECH32_CHARSET[d] for d in combined)


def bech32_decode(bech: str) -> tuple[str, int, list[int]]:
    """Decode a bech32m string. Returns (hrp, witness_version, witness_program)."""
    pos = bech.rfind("1")
    if pos < 1:
        raise ValueError("Invalid bech32 string")
    hrp = bech[:pos]
    data = [_BECH32_CHARSET.index(c) for c in bech[pos + 1:]]
    if not _bech32m_verify_checksum(hrp, data):
        raise ValueError("Invalid bech32m checksum")
    data = data[:-6]
    witver = data[0]
    witprog = _convertbits(data[1:], 5, 8, pad=False)
    return hrp, witver, witprog


def npub_encode(pubkey_bytes: bytes) -> str:
    """Encode a 32-byte public key as an npub bech32m string (NIP-19)."""
    if len(pubkey_bytes) != 32:
        raise ValueError(f"Public key must be 32 bytes, got {len(pubkey_bytes)}")
    return bech32_encode("npub", 0, list(pubkey_bytes))


def npub_decode(npub: str) -> bytes:
    """Decode an npub bech32m string to raw 32-byte public key."""
    hrp, witver, witprog = bech32_decode(npub)
    if hrp != "npub":
        raise ValueError(f"Expected npub prefix, got {hrp}")
    if witver != 0:
        raise ValueError(f"Expected witness version 0, got {witver}")
    return bytes(witprog)


def nsec_encode(seckey_bytes: bytes) -> str:
    """Encode a 32-byte secret key as an nsec bech32m string (NIP-19)."""
    if len(seckey_bytes) != 32:
        raise ValueError(f"Secret key must be 32 bytes, got {len(seckey_bytes)}")
    return bech32_encode("nsec", 0, list(seckey_bytes))


def nsec_decode(nsec: str) -> bytes:
    """Decode an nsec bech32m string to raw 32-byte secret key."""
    hrp, witver, witprog = bech32_decode(nsec)
    if hrp != "nsec":
        raise ValueError(f"Expected nsec prefix, got {hrp}")
    if witver != 0:
        raise ValueError(f"Expected witness version 0, got {witver}")
    return bytes(witprog)


# --- NostrIdentity ----------------------------------------------------------


@dataclass
class NostrIdentity:
    """A Nostr-compatible identity: Ed25519 keypair with hex/bech32 encoding.

    NIP-01: The public key is a 32-byte hex string used as the
    user's identifier. NIP-19 adds human-readable bech32 encoding.

    This identity can sign and verify Nostr events. The private key
    is never exposed in logs, string representations, or error messages.
    """

    _private_key: Ed25519PrivateKey
    _public_key: Ed25519PublicKey
    _public_key_bytes: bytes
    _private_key_bytes: bytes

    @property
    def x25519_private_key_bytes(self) -> bytes:
        """Raw 32-byte X25519 private key bytes (derived from Ed25519 seed)."""
        from cryptography.hazmat.primitives.serialization import (
            Encoding, NoEncryption, PrivateFormat,
        )
        from .encryption import _ed25519_to_x25519_private
        x25519_key = _ed25519_to_x25519_private(self._private_key_bytes)
        return x25519_key.private_bytes(
            encoding=Encoding.Raw,
            format=PrivateFormat.Raw,
            encryption_algorithm=NoEncryption(),
        )

    @property
    def x25519_public_key_bytes(self) -> bytes:
        """Raw 32-byte X25519 public key bytes (derived from Ed25519 seed)."""
        from .encryption import _x25519_public_from_ed25519
        return _x25519_public_from_ed25519(self._private_key_bytes)

    @property
    def public_key_hex(self) -> str:
        """32-byte hex public key (NIP-01)."""
        return self._public_key_bytes.hex()

    @property
    def public_key_bech32(self) -> str:
        """Human-readable bech32-encoded public key (NIP-19 npub)."""
        return npub_encode(self._public_key_bytes)

    @property
    def secret_key_hex(self) -> str:
        """32-byte hex secret key (NIP-01)."""
        return self._private_key_bytes.hex()

    @property
    def secret_key_bech32(self) -> str:
        """Human-readable bech32-encoded secret key (NIP-19 nsec)."""
        return nsec_encode(self._private_key_bytes)

    def sign(self, data: bytes) -> bytes:
        """Sign data with the Ed25519 private key. Returns 64-byte signature."""
        return self._private_key.sign(data)

    def verify(self, signature: bytes, data: bytes) -> bool:
        """Verify an Ed25519 signature. Returns True if valid."""
        try:
            self._public_key.verify(signature, data)
            return True
        except Exception:
            return False

    @classmethod
    def from_secret_key(cls, secret_key_bytes: bytes) -> NostrIdentity:
        """Create an identity from a 32-byte secret key (NIP-01)."""
        if len(secret_key_bytes) != 32:
            raise ValueError(f"Secret key must be 32 bytes, got {len(secret_key_bytes)}")
        private_key = Ed25519PrivateKey.from_private_bytes(secret_key_bytes)
        public_key = private_key.public_key()
        public_key_bytes = public_key.public_bytes(
            encoding=Encoding.Raw, format=PublicFormat.Raw
        )
        return cls(
            _private_key=private_key,
            _public_key=public_key,
            _public_key_bytes=public_key_bytes,
            _private_key_bytes=secret_key_bytes,
        )

    @classmethod
    def generate(cls) -> NostrIdentity:
        """Generate a fresh random identity."""
        private_key = Ed25519PrivateKey.generate()
        private_key_bytes = private_key.private_bytes(
            encoding=Encoding.Raw,
            format=PrivateFormat.Raw,
            encryption_algorithm=NoEncryption(),
        )
        return cls.from_secret_key(private_key_bytes)

    def __repr__(self) -> str:
        """Safe repr: never exposes private key material."""
        return f"NostrIdentity(pubkey={self.public_key_hex[:16]}...)"


def generate_nostr_identity() -> NostrIdentity:
    """Generate a new Nostr identity."""
    return NostrIdentity.generate()


def nostr_identity_from_seed(seed: bytes) -> NostrIdentity:
    """Derive a Nostr identity from an Ed25519 seed.

    Since Nostr uses Ed25519, we can derive a compatible identity from
    the same seed material. This enables migration from other systems
    that use Ed25519 keys.
    """
    return NostrIdentity.from_secret_key(seed)


__all__ = [
    "NostrIdentity",
    "bech32_decode",
    "bech32_encode",
    "generate_nostr_identity",
    "npub_decode",
    "npub_encode",
    "nostr_identity_from_seed",
    "nsec_decode",
    "nsec_encode",
]
