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
    nostr_identity_from_narada_seed,
    nostr_identity_to_narada_pubid,
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
    # nsec1... should not decode as npub
    from src.nostr.identity import generate_nostr_identity
    identity = generate_nostr_identity()
    nsec = identity.secret_key_bech32
    with pytest.raises(ValueError, match="nsec"):
        npub_decode(nsec)


def test_npub_decode_invalid_bech32():
    with pytest.raises(ValueError):
        npub_decode("npub1invalidbech32")


def test_nostr_identity_from_narada_seed():
    import secrets
    seed = secrets.token_bytes(32)
    identity = nostr_identity_from_narada_seed(seed)
    assert len(identity.public_key_hex) == 64
    # Same seed should produce same identity
    identity2 = nostr_identity_from_narada_seed(seed)
    assert identity.public_key_hex == identity2.public_key_hex


def test_nostr_identity_to_narada_pubid():
    import secrets
    seed = secrets.token_bytes(32)
    identity = nostr_identity_from_narada_seed(seed)
    pubid = nostr_identity_to_narada_pubid(identity)
    assert pubid.startswith("narada1")
    # The public id should be deterministically derived
    pubid2 = nostr_identity_to_narada_pubid(identity)
    assert pubid == pubid2


def test_multiple_identities_are_unique():
    id1 = generate_nostr_identity()
    id2 = generate_nostr_identity()
    assert id1.public_key_hex != id2.public_key_hex
