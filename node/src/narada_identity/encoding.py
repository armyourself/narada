"""Encoding for Narada identities.

A Narada identity is encoded as a ``narada1...`` bech32m string. The
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
from typing import Optional

from .errors import NaradaIdentityError
_HRP = "narada"
_VERSION_V1 = 0x01
_VERSION_V2 = 0x02
_PAYLOAD_LEN_V1 = 65
_MAX_HINT_BYTES = 255  # max node-id hint length we encode in V2
_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


class IdentityVersion(Enum):
    """Versions of the on-the-wire Narada identity payload.

    V1: [ver=1][ed25519 32B][x25519 32B] (65 bytes)
    V2: same as V1 followed by one or more TLV fields. The first
        defined TLV is ``NODE_ID_HINT = 0x01`` carrying the bech32m
        ``node1...`` id of the user's home node. Senders use this to
        resolve a recipient's mailbox without an explicit directory
        lookup.
    """

    V1 = _VERSION_V1
    V2 = _VERSION_V2
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
        raise NaradaIdentityError("Invalid character in bech32 string")
    if bech.lower() != bech and bech.upper() != bech:
        raise NaradaIdentityError("Mixed case in bech32 string")
    bech = bech.lower()
    pos = bech.rfind("1")
    if pos < 1 or pos + 7 > len(bech) or len(bech) > 1023:
        raise NaradaIdentityError("Invalid bech32 length or position of '1'")
    hrp = bech[:pos]
    data = []
    for c in bech[pos + 1:]:
        if c not in _CHARSET:
            raise NaradaIdentityError(f"Invalid bech32 character: {c!r}")
        data.append(_CHARSET.index(c))
    polymod = _polymod(_hrp_expand(hrp) + data)
    if polymod == _BECH32M_CONST:
        spec = "bech32m"
    elif polymod == 1:
        spec = "bech32"
    else:
        raise NaradaIdentityError("Invalid bech32 checksum")
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
            raise NaradaIdentityError("Invalid value for base conversion")
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        raise NaradaIdentityError("Cannot convert without padding")
    return ret

# TLV type byte for the V2 node-id hint.
_TLV_NODE_ID_HINT = 0x01


def _encode_tlv(type_byte: int, value: bytes) -> bytes:
    return bytes([type_byte]) + len(value).to_bytes(2, "big") + value


def _decode_tlv(buf: bytes, offset: int) -> tuple[int, bytes, int]:
    if offset + 3 > len(buf):
        raise NaradaIdentityError("TLV header truncated")
    type_byte = buf[offset]
    length = int.from_bytes(buf[offset + 1 : offset + 3], "big")
    if offset + 3 + length > len(buf):
        raise NaradaIdentityError(f"TLV value truncated: need {length} bytes")
    return type_byte, bytes(buf[offset + 3 : offset + 3 + length]), offset + 3 + length


def encode_public_id(
    ed25519_public_key: bytes,
    x25519_public_key: bytes,
    *,
    version: IdentityVersion = IdentityVersion.V1,
    node_id_hint: Optional[str] = None,
) -> str:
    """Encode a public Narada identity as a ``narada1...`` string.

    V2 identities carry an optional ``node_id_hint`` (the bech32m
    ``node1...`` id of the user's home node). V1 identities ignore
    the hint. The hint lets a sender resolve a recipient's mailbox
    without an explicit directory lookup.
    """
    if len(ed25519_public_key) != 32:
        raise NaradaIdentityError(
            f"Ed25519 public key must be 32 bytes, got {len(ed25519_public_key)}"
        )
    if len(x25519_public_key) != 32:
        raise NaradaIdentityError(
            f"X25519 public key must be 32 bytes, got {len(x25519_public_key)}"
        )
    base = bytes([version.value]) + ed25519_public_key + x25519_public_key
    if version == IdentityVersion.V2 and node_id_hint:
        hint = node_id_hint.encode("ascii")
        if len(hint) > _MAX_HINT_BYTES:
            raise NaradaIdentityError(
                f"node id hint too long: {len(hint)} > {_MAX_HINT_BYTES}"
            )
        payload = base + _encode_tlv(_TLV_NODE_ID_HINT, hint)
    elif version == IdentityVersion.V2:
        payload = base  # V2 with no hint is just 65 bytes; readers treat it as V1
    else:
        if node_id_hint:
            raise NaradaIdentityError("node_id_hint requires IdentityVersion.V2")
        payload = base
    data = _convertbits(payload, 8, 5, pad=True)
    return _bech32_encode(_HRP, data, "bech32m")
def decode_public_id(public_id: str) -> tuple[IdentityVersion, bytes, bytes]:
    """Decode a ``narada1...`` string into ``(version, ed25519_pub, x25519_pub)``.

    Backwards-compatible 3-tuple return. To read the optional
    node-id hint from a V2 identity, call :func:`decode_node_hint`.
    Unknown V2 TLVs are silently skipped (forward compatibility).
    """
    hrp, data, spec = _bech32_decode(public_id)
    if hrp != _HRP:
        raise NaradaIdentityError(f"Expected hrp '{_HRP}', got {hrp!r}")
    if spec != "bech32m":
        raise NaradaIdentityError(
            f"Narada identities must use bech32m, got {spec!r}"
        )
    payload = bytes(_convertbits(data, 5, 8, pad=False))
    if len(payload) < _PAYLOAD_LEN_V1:
        raise NaradaIdentityError(
            f"Expected at least {_PAYLOAD_LEN_V1} bytes, got {len(payload)}"
        )
    try:
        version = IdentityVersion(payload[0])
    except ValueError as exc:
        raise NaradaIdentityError(
            f"Unknown identity version: {payload[0]}"
        ) from exc
    return version, bytes(payload[1:33]), bytes(payload[33:65])


def decode_node_hint(public_id: str) -> Optional[str]:
    """Return the embedded ``node1...`` hint of a V2 identity, or None.

    V1 identities always return None.
    """
    hrp, data, spec = _bech32_decode(public_id)
    if hrp != _HRP or spec != "bech32m":
        return None
    payload = bytes(_convertbits(data, 5, 8, pad=False))
    if len(payload) <= _PAYLOAD_LEN_V1:
        return None
    try:
        version = IdentityVersion(payload[0])
    except ValueError:
        return None
    if version != IdentityVersion.V2:
        return None
    offset = _PAYLOAD_LEN_V1
    while offset < len(payload):
        try:
            t, v, offset = _decode_tlv(payload, offset)
        except NaradaIdentityError:
            return None
        if t == _TLV_NODE_ID_HINT:
            try:
                return v.decode("ascii")
            except UnicodeDecodeError:
                return None
    return None


def is_valid_public_id(public_id: str) -> bool:
    """Return True if ``public_id`` is a syntactically valid Narada identity."""
    try:
        decode_public_id(public_id)
    except NaradaIdentityError:
        return False
    return True


def encode_node_id(ed25519_public_key: bytes) -> str:
    """Encode a Narada node public id (Ed25519-only) as a ``node1...`` string.

    Node identities are distinct from user identities: the user identity
    (in :func:`encode_public_id`) carries both an Ed25519 signing key
    and an X25519 encryption key, and is owned by an account. A node
    identity is owned by a node daemon and only needs to sign, so the
    payload is just the 32-byte Ed25519 public key.
    """
    if len(ed25519_public_key) != 32:
        raise NaradaIdentityError(
            f"Ed25519 public key must be 32 bytes, got {len(ed25519_public_key)}"
        )
    data = _convertbits(ed25519_public_key, 8, 5, pad=True)
    return _bech32_encode("node", data, "bech32m")


def decode_node_id(public_id: str) -> bytes:
    """Decode a ``node1...`` string into a 32-byte Ed25519 public key."""
    hrp, data, spec = _bech32_decode(public_id)
    if hrp != "node":
        raise NaradaIdentityError(f"Expected node hrp 'node', got {hrp!r}")
    if spec != "bech32m":
        raise NaradaIdentityError(
            f"Node identities must use bech32m, got {spec!r}"
        )
    payload = bytes(_convertbits(data, 5, 8, pad=False))
    if len(payload) != 32:
        raise NaradaIdentityError(
            f"Expected payload of 32 bytes, got {len(payload)}"
        )
    return payload


def is_valid_node_id(public_id: str) -> bool:
    try:
        decode_node_id(public_id)
        return True
    except NaradaIdentityError:
        return False


__all__ = [
    "IdentityVersion",
    "decode_public_id",
    "encode_public_id",
    "is_valid_public_id",
    "encode_node_id",
    "decode_node_id",
    "is_valid_node_id",
]
