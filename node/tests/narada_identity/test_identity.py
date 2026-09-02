import os

import pytest

from src.narada_identity.encoding import decode_public_id
from src.narada_identity.errors import NaradaIdentityError
from src.narada_identity.identity import (
    NaradaIdentity,
    generate_identity,
    identity_from_keystore,
    identity_from_mnemonic,
    rotate_identity,
    verify_public_id_signature,
)
from src.narada_identity.keystore import InMemoryKeystore
from src.narada_identity.keypair import (
    generate_keypair,
    keypair_from_seed,
    verify_signature,
)
from src.narada_identity.mnemonic import (
    generate_mnemonic,
    mnemonic_to_seed,
    validate_mnemonic,
)


def test_keypair_generation_yields_distinct_publics():
    a = generate_keypair()
    b = generate_keypair()
    assert a.ed25519_public_bytes != b.ed25519_public_bytes
    assert a.x25519_public_bytes != b.x25519_public_bytes
    assert len(a.ed25519_public_bytes) == 32
    assert len(a.x25519_public_bytes) == 32


def test_keypair_from_seed_is_deterministic():
    seed = os.urandom(32)
    a = keypair_from_seed(seed)
    b = keypair_from_seed(seed)
    assert a.ed25519_public_bytes == b.ed25519_public_bytes
    assert a.x25519_public_bytes == b.x25519_public_bytes


def test_sign_and_verify_roundtrip():
    kp = generate_keypair()
    data = b"hello narada"
    sig = kp.sign(data)
    assert verify_signature(kp.ed25519_public_bytes, sig, data) is True
    assert verify_signature(kp.ed25519_public_bytes, sig, b"tampered") is False


def test_shared_secret_symmetric():
    a = generate_keypair()
    b = generate_keypair()
    s_ab = a.shared_secret_with(b.x25519_public_bytes)
    s_ba = b.shared_secret_with(a.x25519_public_bytes)
    assert s_ab == s_ba
    assert len(s_ab) == 32


def test_mnemonic_roundtrip():
    phrase = generate_mnemonic()
    assert validate_mnemonic(phrase)
    seed = mnemonic_to_seed(phrase)
    assert len(seed) == 32
    kp1 = keypair_from_seed(seed)
    # Re-deriving from the same phrase should give the same key.
    kp2 = keypair_from_seed(mnemonic_to_seed(phrase))
    assert kp1.ed25519_public_bytes == kp2.ed25519_public_bytes
    assert kp1.x25519_public_bytes == kp2.x25519_public_bytes


def test_mnemonic_invalid_raises():
    with pytest.raises(NaradaIdentityError):
        mnemonic_to_seed("not a valid bip39 phrase at all")


def test_generate_identity_returns_mnemonic(in_memory_keystore: InMemoryKeystore):
    identity, mnemonic = generate_identity("alice@example.com", keystore=in_memory_keystore)
    assert isinstance(identity, NaradaIdentity)
    assert identity.account_id == "alice@example.com"
    assert identity.public_id.startswith("narada1")
    assert validate_mnemonic(mnemonic)
    # The keystore now holds the seed.
    assert in_memory_keystore.has("alice@example.com")


def test_identity_from_mnemonic_matches_generate(in_memory_keystore: InMemoryKeystore):
    _id, mnemonic = generate_identity("bob@example.com", keystore=in_memory_keystore)
    recovered = identity_from_mnemonic("bob@example.com", mnemonic, keystore=in_memory_keystore)
    assert recovered.public_id == _id.public_id


def test_identity_from_keystore_roundtrip(in_memory_keystore: InMemoryKeystore):
    identity, _ = generate_identity("carol@example.com", keystore=in_memory_keystore)
    loaded = identity_from_keystore("carol@example.com", in_memory_keystore)
    assert loaded.public_id == identity.public_id


def test_rotate_identity_changes_public_id(in_memory_keystore: InMemoryKeystore):
    original, _ = generate_identity("dave@example.com", keystore=in_memory_keystore)
    rotated, _ = rotate_identity("dave@example.com", in_memory_keystore)
    assert rotated.public_id != original.public_id
    # Re-loading from the keystore gives the rotated identity.
    reloaded = identity_from_keystore("dave@example.com", in_memory_keystore)
    assert reloaded.public_id == rotated.public_id


def test_rotate_identity_without_existing_raises(in_memory_keystore: InMemoryKeystore):
    with pytest.raises(NaradaIdentityError):
        rotate_identity("ghost@example.com", in_memory_keystore)


def test_shared_secret_with_public_id_roundtrip():
    alice, _ = generate_identity("alice@example.com")
    bob, _ = generate_identity("bob@example.com")
    s_alice = alice.shared_secret_with(bob.public_id)
    s_bob = bob.shared_secret_with(alice.public_id)
    assert s_alice == s_bob
    # Bad peer id rejected.
    with pytest.raises(NaradaIdentityError):
        alice.shared_secret_with("not-a-real-id")


def test_verify_public_id_signature():
    alice, _ = generate_identity("alice@example.com")
    msg = b"hello from alice"
    sig = alice.sign(msg)
    assert verify_public_id_signature(alice.public_id, sig, msg) is True
    assert verify_public_id_signature(alice.public_id, sig, b"other") is False


def test_decode_public_id_returns_consistent_keys():
    identity, _ = generate_identity("eve@example.com")
    version, ed_pub, x_pub = decode_public_id(identity.public_id)
    assert version.name == "V1"
    assert ed_pub == identity.keypair.ed25519_public_bytes
    assert x_pub == identity.keypair.x25519_public_bytes
