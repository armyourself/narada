"""Tests for Nostr identity (NIP-01/NIP-19)."""

from __future__ import annotations

import pytest

from src.nostr.identity import (
    NostrIdentity,
    generate_nostr_identity,
    npub_encode,
    npub_decode,
    nsec_encode,
    nsec_decode,
    nostr_identity_from_seed,
)


def test_generate_identity():
    identity = generate_nostr_identity()
    assert len(identity.public_key_hex) == 64
    assert len(identity.secret_key_hex) == 64
    assert identity.public_key_bech32.startswith("npub")
    assert identity.secret_key_bech32.startswith("nsec")


def test_identity_sign_and_verify():
    identity = generate_nostr_identity()
    data = b"hello world"
    sig = identity.sign(data)
    assert len(sig) == 64
    assert identity.verify(sig, data)
    assert not identity.verify(b"\x00" * 64, data)


def test_npub_roundtrip():
    identity = generate_nostr_identity()
    npub = identity.public_key_bech32
    decoded = npub_decode(npub)
    assert decoded == identity._public_key_bytes


def test_nsec_roundtrip():
    identity = generate_nostr_identity()
    nsec = identity.secret_key_bech32
    decoded = nsec_decode(nsec)
    assert decoded == identity._private_key_bytes


def test_from_secret_key():
    identity = generate_nostr_identity()
    restored = NostrIdentity.from_secret_key(identity._private_key_bytes)
    assert restored.public_key_hex == identity.public_key_hex


def test_from_secret_key_wrong_length():
    with pytest.raises(ValueError, match="32 bytes"):
        NostrIdentity.from_secret_key(b"\x00" * 16)


def test_npub_encode_decode_roundtrip():
    import secrets
    key = secrets.token_bytes(32)
    npub = npub_encode(key)
    assert npub.startswith("npub")
    decoded = npub_decode(npub)
    assert decoded == key


def test_nsec_encode_decode_roundtrip():
    import secrets
    key = secrets.token_bytes(32)
    nsec = nsec_encode(key)
    assert nsec.startswith("nsec")
    decoded = nsec_decode(nsec)
    assert decoded == key


def test_repr_does_not_expose_secret():
    identity = generate_nostr_identity()
    r = repr(identity)
    assert identity.secret_key_hex not in r
    assert identity._private_key_bytes.hex() not in r
    assert "NostrIdentity" in r


def test_npub_decode_wrong_prefix():
    from src.nostr.identity import generate_nostr_identity
    identity = generate_nostr_identity()
    nsec = identity.secret_key_bech32
    with pytest.raises(ValueError, match="nsec"):
        npub_decode(nsec)


def test_npub_decode_invalid_bech32():
    with pytest.raises(ValueError):
        npub_decode("npub1invalidbech32")


# --- NIP-19 interop (plain bech32, no witness version) ---------------------

_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _ref_polymod(values):
    """BIP-173 reference polymod (independent implementation)."""
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            chk ^= gen[i] if ((top >> i) & 1) else 0
    return chk


def _ref_hrp_expand(hrp):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _ref_bech32_create_checksum(hrp, data):
    values = _ref_hrp_expand(hrp) + data
    polymod = _ref_polymod(values + [0] * 6) ^ 1  # bech32 const = 1
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def _ref_convertbits(data, frombits, tobits, pad=True):
    acc = bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    for value in data:
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad and bits:
        ret.append((acc << (tobits - bits)) & maxv)
    return ret


def _ref_npub_encode(pubkey: bytes) -> str:
    """Reference NIP-19 npub: plain bech32, no witness-version prefix."""
    data = _ref_convertbits(pubkey, 8, 5)
    combined = data + _ref_bech32_create_checksum("npub", data)
    return "npub1" + "".join(_CHARSET[d] for d in combined)


def test_npub_matches_reference_nip19_encoding():
    import secrets
    key = secrets.token_bytes(32)
    assert npub_encode(key) == _ref_npub_encode(key)


def test_npub_length_is_63_chars():
    import secrets
    npub = npub_encode(secrets.token_bytes(32))
    # "npub1" (5) + 52 data groups + 6 checksum chars, no witness version
    assert len(npub) == 63


def test_bech32m_checksummed_npub_is_rejected():
    # Old bug: checksum used bech32m constant 0x2bc830a3. Such strings
    # must no longer decode — other clients can only read plain bech32.
    import secrets
    key = secrets.token_bytes(32)
    data = _ref_convertbits(key, 8, 5)
    values = _ref_hrp_expand("npub") + data
    polymod = _ref_polymod(values + [0] * 6) ^ 0x2BC830A3
    checksum = [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]
    bad = "npub1" + "".join(_CHARSET[d] for d in data + checksum)
    with pytest.raises(ValueError, match="checksum"):
        npub_decode(bad)


def test_reference_npub_decodes_to_same_key():
    import secrets
    key = secrets.token_bytes(32)
    assert npub_decode(_ref_npub_encode(key)) == key


def test_mixed_case_npub_rejected():
    import secrets
    npub = npub_encode(secrets.token_bytes(32))
    mixed = npub[:10].upper() + npub[10:]
    with pytest.raises(ValueError, match="[Mm]ixed"):
        npub_decode(mixed)


def test_nostr_identity_from_seed():
    import secrets
    seed = secrets.token_bytes(32)
    identity = nostr_identity_from_seed(seed)
    assert len(identity.public_key_hex) == 64
    # Same seed should produce same identity
    identity2 = nostr_identity_from_seed(seed)
    assert identity.public_key_hex == identity2.public_key_hex


def test_multiple_identities_are_unique():
    id1 = generate_nostr_identity()
    id2 = generate_nostr_identity()
    assert id1.public_key_hex != id2.public_key_hex
