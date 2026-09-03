"""Tests for the inbox's rotation-aware behavior (Phase 1 key rotation).

The inbox is the receiver-side helper for incoming Narada
envelopes. With the Phase 1 wire rotation, the inbox must:

1. Detect v=3 envelopes as key-update announcements and persist
   the rotation via the supplied KeyRotationStore instead of the
   regular mailbox.
2. For v=1 envelopes whose sender has an active rotation record,
   verify the signature under the rotation's new ed25519 key.
   The body is still decrypted with the recipient's identity
   (whose X25519 key is unchanged by Option A rotation).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.narada.envelope import NaradaBody, make_envelope
from src.narada.inbox import NaradaInbox
from src.narada.key_rotation_store import KeyRotationStore
from src.narada.key_update import make_key_update_envelope
from src.narada_identity.identity import (
    generate_identity,
    identity_from_keystore_with_preserved_x25519,
    rotate_identity_preserve_x25519,
)
from src.narada_identity.keystore import InMemoryKeystore


def _hmac_key() -> bytes:
    return b"K" * 32


def _two_accounts():
    """Alice and Bob, both Option-A-capable."""
    ks_alice = InMemoryKeystore()
    ks_bob = InMemoryKeystore()
    alice_old, _ = generate_identity("alice@example.com", keystore=ks_alice)
    bob, _ = generate_identity("bob@example.com", keystore=ks_bob)
    return ks_alice, alice_old, ks_bob, bob


# --- v=3 key update detection --------------------------------------


def test_inbox_accepts_v3_key_update(tmp_path: Path):
    ks_alice, alice_old, ks_bob, bob = _two_accounts()
    # Alice rotates.
    alice_new, _ = rotate_identity_preserve_x25519("alice@example.com", ks_alice)
    # Alice sends the key update to Bob.
    update_env = make_key_update_envelope(alice_old, bob.public_id, alice_new)

    rotation_path = tmp_path / "rot.json"
    rot_store = KeyRotationStore(rotation_path, key=_hmac_key())
    inbox = NaradaInbox("bob@example.com", keystore=ks_bob, rotation_store=rot_store)
    body, was_dup, is_key_update = inbox.receive(update_env)
    assert is_key_update is True
    assert was_dup is False
    assert body.prior_public_id == alice_old.public_id
    assert body.new_public_id == alice_new.public_id
    # Rotation is persisted.
    rec = rot_store.lookup(alice_old.public_id)
    assert rec is not None
    assert rec.new_public_id == alice_new.public_id


def test_inbox_does_not_persist_key_update_to_mailbox(tmp_path: Path):
    ks_alice, alice_old, ks_bob, bob = _two_accounts()
    alice_new, _ = rotate_identity_preserve_x25519("alice@example.com", ks_alice)
    update_env = make_key_update_envelope(alice_old, bob.public_id, alice_new)

    rot_store = KeyRotationStore(tmp_path / "rot.json", key=_hmac_key())
    data_dir = tmp_path / "data"
    inbox = NaradaInbox(
        "bob@example.com", keystore=ks_bob, rotation_store=rot_store, data_dir=data_dir
    )
    inbox.receive(update_env)
    # Mailbox file does NOT exist (or is empty).
    mailbox = data_dir / "etc" / "mailbox.bob@example.com.jsonl"
    assert not mailbox.exists() or mailbox.read_text() == ""


def test_inbox_dedups_repeat_v3_key_update(tmp_path: Path):
    ks_alice, alice_old, ks_bob, bob = _two_accounts()
    alice_new, _ = rotate_identity_preserve_x25519("alice@example.com", ks_alice)
    update_env = make_key_update_envelope(alice_old, bob.public_id, alice_new)

    rot_store = KeyRotationStore(tmp_path / "rot.json", key=_hmac_key())
    inbox = NaradaInbox("bob@example.com", keystore=ks_bob, rotation_store=rot_store)
    _, was_dup1, is_ku1 = inbox.receive(update_env)
    _, was_dup2, is_ku2 = inbox.receive(update_env)
    assert was_dup1 is False
    assert was_dup2 is True
    assert is_ku1 is True and is_ku2 is True


def test_inbox_rejects_v3_without_rotation_store(tmp_path: Path):
    from src.narada.envelope import NaradaEnvelopeError

    ks_alice, alice_old, ks_bob, bob = _two_accounts()
    alice_new, _ = rotate_identity_preserve_x25519("alice@example.com", ks_alice)
    update_env = make_key_update_envelope(alice_old, bob.public_id, alice_new)

    inbox = NaradaInbox("bob@example.com", keystore=ks_bob)  # no rotation_store
    with pytest.raises(NaradaEnvelopeError):
        inbox.receive(update_env)


# --- Rotation-aware v=1 signature verification ---------------------


def test_inbox_accepts_v1_envelope_from_rotated_sender(tmp_path: Path):
    """After a rotation announcement, an envelope signed with the
    new key (sender_public_id unchanged) must be accepted.
    """
    ks_alice, alice_old, ks_bob, bob = _two_accounts()
    alice_new, _ = rotate_identity_preserve_x25519("alice@example.com", ks_alice)

    # Bob receives the key update first so the rotation is known.
    rot_store = KeyRotationStore(tmp_path / "rot.json", key=_hmac_key())
    inbox = NaradaInbox("bob@example.com", keystore=ks_bob, rotation_store=rot_store)
    update_env = make_key_update_envelope(alice_old, bob.public_id, alice_new)
    inbox.receive(update_env)

    # Now Alice (new) sends a regular v=1 envelope to Bob.
    body = NaradaBody(subject="after rotation", body_text="hi")
    env = make_envelope(alice_new, bob.public_id, body)

    opened, was_dup, is_ku = inbox.receive(env)
    assert is_ku is False
    assert was_dup is False
def test_inbox_rejects_v3_whose_not_after_is_in_the_past(tmp_path: Path):
    """A v=3 envelope whose not_after has already passed is rejected
    by the inbox: the rotation window has closed, so the
    announcement is no longer useful (and accepting it would
    extend trust to a key that was supposed to be off the air).
    """
    import time
    from src.narada.envelope import NaradaEnvelopeError
    from src.narada_identity.identity import generate_identity, rotate_identity_preserve_x25519

    ks_alice, alice_old, ks_bob, bob = _two_accounts()
    alice_new, _ = rotate_identity_preserve_x25519("alice@example.com", ks_alice)
    rot_store = KeyRotationStore(tmp_path / "rot.json", key=_hmac_key())
    inbox = NaradaInbox("bob@example.com", keystore=ks_bob, rotation_store=rot_store)
    # not_after = 1 second in the past.
    update_env = make_key_update_envelope(
        alice_old, bob.public_id, alice_new, not_after=int(time.time()) - 1
    )
    with pytest.raises(NaradaEnvelopeError):
        inbox.receive(update_env)


def test_inbox_v1_no_rotation_still_works(tmp_path: Path):
    """Backwards compat: a v=1 envelope from a sender with no
    rotation record is accepted under the prior key (the original
    Phase 2 path).
    """
    ks_alice, alice_old, ks_bob, bob = _two_accounts()
    rot_store = KeyRotationStore(tmp_path / "rot.json", key=_hmac_key())
    inbox = NaradaInbox("bob@example.com", keystore=ks_bob, rotation_store=rot_store)
    body = NaradaBody(subject="hi", body_text="hello")
    env = make_envelope(alice_old, bob.public_id, body)
    opened, was_dup, is_ku = inbox.receive(env)
    assert is_ku is False
    assert was_dup is False
    assert opened.subject == "hi"
def test_inbox_rejects_v1_with_invalid_signature_under_either_key(tmp_path: Path):
    """If a v=1 envelope's signature fails under both the prior
    ed25519 and the rotation's new ed25519, the inbox rejects it.
    """
    from src.narada.envelope import NaradaEnvelope, NaradaEnvelopeError
    from src.narada_identity.encoding import decode_public_id
    from src.narada_identity.keypair import keypair_from_seed

    ks_alice, alice_old, ks_bob, bob = _two_accounts()
    alice_new, _ = rotate_identity_preserve_x25519("alice@example.com", ks_alice)
    rot_store = KeyRotationStore(tmp_path / "rot.json", key=_hmac_key())
    inbox = NaradaInbox("bob@example.com", keystore=ks_bob, rotation_store=rot_store)
    rot_store.record(
        prior_public_id=alice_old.public_id,
        new_public_id=alice_new.public_id,
        not_after=int(__import__("time").time()) + 1000,
    )
    # Build an envelope with a wrong signature.
    body = NaradaBody(subject="x")
    env = make_envelope(alice_new, bob.public_id, body)
    bad_env = NaradaEnvelope(
        v=env.v,
        sender_public_id=env.sender_public_id,
        recipient_public_id=env.recipient_public_id,
        message_id=env.message_id,
        timestamp=env.timestamp,
        nonce=env.nonce,
        signature=b"\x00" * 64,  # bogus signature
        body_ciphertext=env.body_ciphertext,
    )
    with pytest.raises(NaradaEnvelopeError):
        inbox.receive(bad_env)


# --- End-to-end: rotate then send ---------------------------


def test_end_to_end_rotate_then_send(tmp_path: Path):
    """Alice rotates, sends a key update to Bob, then sends a
    regular envelope signed with the new key. Bob's inbox
    accepts both.
    """
    ks_alice, alice_old, ks_bob, bob = _two_accounts()

    # Step 1: Alice rotates.
    alice_new, _ = rotate_identity_preserve_x25519("alice@example.com", ks_alice)

    # Step 2: Bob creates an inbox with a rotation store.
    rot_store = KeyRotationStore(tmp_path / "rot.json", key=_hmac_key())
    data_dir = tmp_path / "data"
    inbox = NaradaInbox(
        "bob@example.com", keystore=ks_bob, rotation_store=rot_store, data_dir=data_dir
    )

    # Step 3: Alice's key update arrives at Bob.
    update_env = make_key_update_envelope(alice_old, bob.public_id, alice_new)
    _, _, is_ku1 = inbox.receive(update_env)
    assert is_ku1 is True

    # Step 4: Alice (new) sends a regular envelope to Bob.
    env = make_envelope(
        alice_new, bob.public_id, NaradaBody(subject="after-rotation", body_text="hi")
    )
    opened, was_dup, is_ku2 = inbox.receive(env)
    assert is_ku2 is False
    assert was_dup is False
    assert opened.subject == "after-rotation"
    assert opened.body_text == "hi"

    # The mailbox has the regular envelope.
    mailbox = data_dir / "etc" / "mailbox.bob@example.com.jsonl"
    assert mailbox.exists()
    contents = mailbox.read_text()
    assert "after-rotation" in contents
    assert "hi" in contents
    # The mailbox does NOT contain the key update.
    assert "__narada_key_update__" not in contents


def test_preserved_x25519_keypair_works_after_reload(tmp_path: Path):
    """After rotation, the new identity (loaded via the preserved
    path) must be able to decrypt a new envelope sealed to the
    prior recipient. The X25519 half is the same.
    """
    from src.narada.envelope import open_envelope

    ks_alice = InMemoryKeystore()
    alice_old, _ = generate_identity("alice@example.com", keystore=ks_alice)
    rotate_identity_preserve_x25519("alice@example.com", ks_alice)
    alice_reloaded = identity_from_keystore_with_preserved_x25519(
        "alice@example.com", ks_alice
    )
    ks_bob = InMemoryKeystore()
    bob, _ = generate_identity("bob@example.com", keystore=ks_bob)
    body = NaradaBody(subject="hi", body_text="hello")
    env = make_envelope(alice_reloaded, bob.public_id, body)
    opened = open_envelope(env, bob)
    assert opened.subject == "hi"