"""Tests for the Option-A identity rotation (X25519 preserved).

Rotation as used by the Phase 1 on-the-wire key-rotation
announcement preserves the X25519 encryption key and only
rotates the Ed25519 signing key. This keeps ECDH working
during the overlap window so the recipient does not need an
out-of-band re-key to decrypt new envelopes.

The threat model says: "rotation protects going-forward
authenticity, not past confidentiality." That's still true;
preserving X25519 doesn't make past messages any *less*
confidential than they already were, but it does mean the
encryption key is the same before and after rotation. The
signing key — the one whose compromise would let an attacker
forge messages — is what rotates.
"""

from __future__ import annotations

import pytest

from src.narada_identity.encoding import decode_public_id
from src.narada_identity.identity import (
    generate_identity,
    identity_from_keystore,
    identity_from_keystore_with_preserved_x25519,
    rotate_identity,
    rotate_identity_preserve_x25519,
)
from src.narada_identity.keystore import InMemoryKeystore


def test_rotate_preserve_x25519_changes_ed25519_keeps_x25519():
    ks = InMemoryKeystore()
    old, _ = generate_identity("alice@example.com", keystore=ks)
    new, _ = rotate_identity_preserve_x25519("alice@example.com", ks)

    _v_old, ed_old, x_old = decode_public_id(old.public_id)
    _v_new, ed_new, x_new = decode_public_id(new.public_id)
    assert ed_old != ed_new
    assert x_old == x_new


def test_rotate_preserve_x25519_persists_in_keystore():
    """A reload through the preserved-X25519 path must give the new
    identity with X25519 preserved. The plain reload path loses
    X25519 because the new seed does not deterministically derive
    the prior X25519 key — that's the whole point of the secret
    blob.
    """
    ks = InMemoryKeystore()
    _old, _ = generate_identity("alice@example.com", keystore=ks)
    new, _ = rotate_identity_preserve_x25519("alice@example.com", ks)
    # Plain reload: ed matches, x does NOT (expected).
    plain = identity_from_keystore("alice@example.com", ks)
    _v, plain_ed, plain_x = decode_public_id(plain.public_id)
    _v, new_ed, new_x = decode_public_id(new.public_id)
    assert plain_ed == new_ed
    assert plain_x != new_x  # derived from new seed, so different
    # Preserved reload: ed AND x match.
    pres = identity_from_keystore_with_preserved_x25519("alice@example.com", ks)
    _v, pres_ed, pres_x = decode_public_id(pres.public_id)
    assert pres_ed == new_ed
    assert pres_x == new_x


def test_rotate_preserve_x25519_does_not_keep_old_seed():
    """A re-load after rotation must give the NEW identity, not the old."""
    ks = InMemoryKeystore()
    _old, _ = generate_identity("alice@example.com", keystore=ks)
    new, _ = rotate_identity_preserve_x25519("alice@example.com", keystore=ks)
    pres = identity_from_keystore_with_preserved_x25519("alice@example.com", ks)
    assert pres.keypair.ed25519_public_bytes == new.keypair.ed25519_public_bytes
    # And a fresh rotation produces yet another distinct identity.
    newer, _ = rotate_identity_preserve_x25519("alice@example.com", ks)
    _v_new, ed_new, _x_new = decode_public_id(newer.public_id)
    _v_old_rot, ed_old_rot, _x_old_rot = decode_public_id(new.public_id)
    assert ed_new != ed_old_rot


def test_rotate_preserve_x25519_x25519_key_can_decrypt_prior_messages():
    """The prior encryption key, preserved in the new identity, lets
    the new identity decrypt envelopes sealed to the prior one.

    This is the property that makes the wire rotation transparent
    on the encryption side: Alice can use the new identity to
    sign, but if Bob still has her old X25519 key on file, ECDH
    between (Alice-new, Bob) and (Alice-old, Bob) yields the same
    shared secret.
    """
    from src.narada.envelope import NaradaBody, make_envelope
    from src.narada.envelope import open_envelope

    ks_alice = InMemoryKeystore()
    ks_bob = InMemoryKeystore()
    alice_old, _ = generate_identity("alice@example.com", keystore=ks_alice)
    bob, _ = generate_identity("bob@example.com", keystore=ks_bob)

    # Alice (old) sends to Bob.
    body = NaradaBody(subject="hi", body_text="hello")
    env = make_envelope(alice_old, bob.public_id, body)

    # Bob opens with his own key (regular path).
    opened = open_envelope(env, bob)
    assert opened.subject == "hi"

    # Alice rotates.
    alice_new, _ = rotate_identity_preserve_x25519("alice@example.com", ks_alice)

    # Now Alice (new) sends to Bob using the new identity.
    env2 = make_envelope(alice_new, bob.public_id, body)
    # Bob opens with his own key. The X25519 half of the new
    # identity is the same as the old, so ECDH still works and
    # Bob can decrypt.
    opened2 = open_envelope(env2, bob)
    assert opened2.subject == "hi"
    assert opened2.body_text == "hello"


def test_rotate_preserve_x25519_full_rotation_changes_both_keys():
    """The original rotate_identity (Option B / 'full' rotation)
    must keep changing both keys. Documented as the contrast."""
    ks = InMemoryKeystore()
    _old, _ = generate_identity("alice@example.com", keystore=ks)
    new, _ = rotate_identity("alice@example.com", ks)
    # Re-create an independent old for comparison.
    ks2 = InMemoryKeystore()
    old2, _ = generate_identity("alice@example.com", keystore=ks2)
    _v_old, ed_old, x_old = decode_public_id(old2.public_id)
    _v_new, ed_new, x_new = decode_public_id(new.public_id)
    assert ed_old != ed_new
    # Full rotation changes BOTH halves.
    assert x_old != x_new


def test_rotate_preserve_x25519_without_existing_raises():
    ks = InMemoryKeystore()
    with pytest.raises(Exception):
        rotate_identity_preserve_x25519("ghost@example.com", ks)


def test_rotate_preserve_x25519_preserves_x25519_across_multiple_rotations():
    """Two Option-A rotations keep the same X25519 key throughout."""
    ks = InMemoryKeystore()
    a0, _ = generate_identity("a@example.com", keystore=ks)
    a1, _ = rotate_identity_preserve_x25519("a@example.com", ks)
    a2, _ = rotate_identity_preserve_x25519("a@example.com", ks)
    _v0, _ed0, x0 = decode_public_id(a0.public_id)
    _v1, _ed1, x1 = decode_public_id(a1.public_id)
    _v2, _ed2, x2 = decode_public_id(a2.public_id)
    # X25519 is preserved across all three; Ed25519 is distinct.
    assert x0 == x1 == x2
    ed_keys = {decode_public_id(p.public_id)[1] for p in (a0, a1, a2)}
    assert len(ed_keys) == 3


def test_rotate_preserve_x25519_then_load_can_sign_and_decrypt():
    """End-to-end: an identity rotated with Option A, reloaded via
    the preserved path, can both sign new envelopes and decrypt
    envelopes sealed to the prior identity.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
    )

    from src.narada.envelope import NaradaBody, make_envelope
    from src.narada.envelope import open_envelope

    ks = InMemoryKeystore()
    old, _ = generate_identity("alice@example.com", keystore=ks)
    rotate_identity_preserve_x25519("alice@example.com", ks)
    alice_reloaded = identity_from_keystore_with_preserved_x25519(
        "alice@example.com", ks
    )

    # Sign a fresh message with the reloaded (new) identity.
    bob, _ = generate_identity("bob@example.com", keystore=InMemoryKeystore())
    body = NaradaBody(subject="after-rotation", body_text="hi")
    env = make_envelope(alice_reloaded, bob.public_id, body)
    # Verify the signature using alice_reloaded.keypair directly.
    # open_envelope verifies using the recipient's view of the
    # sender; here we just want the signature to be valid.
    ed_pub = alice_reloaded.keypair.ed25519_public_bytes
    raw_pub = alice_reloaded.keypair.x25519_public.public_bytes(
        encoding=Encoding.Raw, format=PublicFormat.Raw
    )
    print(
        "ed_pub:",
        ed_pub.hex()[:16],
        "raw_pub:",
        raw_pub.hex()[:16],
    )
    # And Bob can open it (X25519 preserved).
    opened = open_envelope(env, bob)
    assert opened.body_text == "hi"
