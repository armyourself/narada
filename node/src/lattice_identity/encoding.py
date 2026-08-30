"""Encoding for Lattice identities.

A Lattice identity is encoded as a ``lattice1...`` bech32m string. The
payload is:

    [1 byte  version = 0x01]
    [32 bytes Ed25519 public key (signing)]
    [32 bytes X25519 public key (encryption)]

Total payload length: 65 bytes. Bech32m (BIP-350) is used so the checksum
is unambiguous and forward-compatible with future format changes.

See ``protocol/identity.md`` for the full spec.
"""

from __future__ import annotations

from enum import Enum

from .errors import LatticeIdentityError

_HRP = "lattice"
_VERSION = 0x01
_PAYLOAD_LEN = 65
_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


class IdentityVersion(Enum):
    """Versions of the on-the-wire Lattice identity payload."""

    V1 = _VERSION


# Reference bech32m implementation, following BIP-350. Kept local to avoid
# adding a dependency for a 100-line algorithm.


_BECH32M_CONST = 0x2BC830A3


def _polymod(values: list[int]) -> int:
    GEN = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            chk ^= GEN[i] if ((b >> i) & 1) else 0
    return chk


def _hrp_expand(hrp: str) -> list[int]:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _bech32_encode(hrp: str, data: list[int], spec: str) -> str:
    """Encode a bech32/bech32m string. ``spec`` is 'bech32' or 'bech32m'."""
    combined = data + [0] * 6
    polymod_const = _BECH32M_CONST if spec == "bech32m" else 1
    polymod = _polymod(_hrp_expand(hrp) + combined) ^ polymod_const
    charset = _CHARSET
    return hrp + "1" + "".join(charset[d] for d in data) + "".join(
        charset[(polymod >> 5 * (5 - i)) & 31] for i in range(6)
    )


def _bech32_decode(bech: str) -> tuple[str, list[int], str]:
    """Decode a bech32/bech32m string. Returns (hrp, data, spec)."""
    if any(ord(x) < 33 or ord(x) > 126 for x in bech):
        raise LatticeIdentityError("Invalid character in bech32 string")
    if bech.lower() != bech and bech.upper() != bech:
        raise LatticeIdentityError("Mixed case in bech32 string")
    bech = bech.lower()
    pos = bech.rfind("1")
    if pos < 1 or pos + 7 > len(bech) or len(bech) > 1023:
        raise LatticeIdentityError("Invalid bech32 length or position of '1'")
    hrp = bech[:pos]
    data = []
    for c in bech[pos + 1:]:
        if c not in _CHARSET:
            raise LatticeIdentityError(f"Invalid bech32 character: {c!r}")
        data.append(_CHARSET.index(c))
    polymod = _polymod(_hrp_expand(hrp) + data)
    if polymod == _BECH32M_CONST:
        spec = "bech32m"
    elif polymod == 1:
        spec = "bech32"
    else:
        raise LatticeIdentityError("Invalid bech32 checksum")
    return hrp, data[:-6], spec


def _convertbits(data: bytes | list[int], frombits: int, tobits: int, pad: bool = True) -> list[int]:
    """General power-of-2 base conversion."""
    acc = 0
    bits = 0
    ret: list[int] = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            raise LatticeIdentityError("Invalid value for base conversion")
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        raise LatticeIdentityError("Cannot convert without padding")
    return ret


def encode_public_id(
    ed25519_public_key: bytes,
    x25519_public_key: bytes,
    *,
    version: IdentityVersion = IdentityVersion.V1,
) -> str:
    """Encode a public Lattice identity as a ``lattice1...`` string."""
    if len(ed25519_public_key) != 32:
        raise LatticeIdentityError(
            f"Ed25519 public key must be 32 bytes, got {len(ed25519_public_key)}"
        )
    if len(x25519_public_key) != 32:
        raise LatticeIdentityError(
            f"X25519 public key must be 32 bytes, got {len(x25519_public_key)}"
        )
    payload = bytes([version.value]) + ed25519_public_key + x25519_public_key
    if len(payload) != _PAYLOAD_LEN:
        # Defensive: explicit check so this also holds under ``python -O``.
        raise LatticeIdentityError(
            f"Internal error: payload length is {len(payload)}, expected {_PAYLOAD_LEN}"
        )
    data = _convertbits(payload, 8, 5, pad=True)
    return _bech32_encode(_HRP, data, "bech32m")


def decode_public_id(public_id: str) -> tuple[IdentityVersion, bytes, bytes]:
    """Decode a ``lattice1...`` string into ``(version, ed25519_pub, x25519_pub)``."""
    hrp, data, spec = _bech32_decode(public_id)
    if hrp != _HRP:
        raise LatticeIdentityError(f"Expected hrp '{_HRP}', got {hrp!r}")
    if spec != "bech32m":
        raise LatticeIdentityError(
            f"Lattice identities must use bech32m, got {spec!r}"
        )
    payload = bytes(_convertbits(data, 5, 8, pad=False))
    if len(payload) != _PAYLOAD_LEN:
        raise LatticeIdentityError(
            f"Expected payload of {_PAYLOAD_LEN} bytes, got {len(payload)}"
        )
    try:
        version = IdentityVersion(payload[0])
    except ValueError as exc:
        raise LatticeIdentityError(
            f"Unknown identity version: {payload[0]}"
        ) from exc
    return version, payload[1:33], payload[33:65]


def is_valid_public_id(public_id: str) -> bool:
    """Return True if ``public_id`` is a syntactically valid Lattice identity."""
    try:
        decode_public_id(public_id)
    except LatticeIdentityError:
        return False
    return True


__all__ = [
    "IdentityVersion",
    "decode_public_id",
    "encode_public_id",
    "is_valid_public_id",
]
