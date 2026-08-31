"""Tests for the Lattice inbox (receive + persist)."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from src.lattice.envelope import LatticeBody, make_envelope
from src.lattice.inbox import LatticeInbox
from src.lattice_identity.identity import generate_identity
from src.lattice_identity.keystore import InMemoryKeystore


def _alice_bob():
    ks = InMemoryKeystore()
    alice, _ = generate_identity("alice@example.com", keystore=ks)
    bob, _ = generate_identity("bob@example.com", keystore=ks)
    return ks, alice, bob


def test_receive_happy_path():
    ks, alice, bob = _alice_bob()
    body = LatticeBody(
        subject="hi",
        sender="alice",
        to=("bob@example.com",),
        body_text="hello",
        sent_at=1700000000,
    )
    envelope = make_envelope(alice, bob.public_id, body)
    with tempfile.TemporaryDirectory() as tmp:
        seen = Path(tmp) / "seen.json"
        inbox = LatticeInbox("bob@example.com", keystore=ks, seen_path=seen)
        opened, was_dup = inbox.receive(envelope)
    assert was_dup is False
    assert opened.subject == "hi"
    assert opened.body_text == "hello"


def test_receive_is_idempotent_within_window():
    ks, alice, bob = _alice_bob()
    envelope = make_envelope(alice, bob.public_id, LatticeBody(subject="hi"))
    with tempfile.TemporaryDirectory() as tmp:
        seen = Path(tmp) / "seen.json"
        inbox = LatticeInbox("bob@example.com", keystore=ks, seen_path=seen)
        _, was_dup_1 = inbox.receive(envelope)
        _, was_dup_2 = inbox.receive(envelope)
    assert was_dup_1 is False
    assert was_dup_2 is True


def test_receive_rejects_tampered_envelope():
    from src.lattice.envelope import LatticeEnvelope, LatticeEnvelopeError

    ks, alice, bob = _alice_bob()
    envelope = make_envelope(alice, bob.public_id, LatticeBody(subject="hi"))
    bad = LatticeEnvelope(
        v=envelope.v,
        sender_public_id=envelope.sender_public_id,
        recipient_public_id=envelope.recipient_public_id,
        message_id=envelope.message_id,
        timestamp=envelope.timestamp,
        nonce=envelope.nonce,
        signature=envelope.signature,
        body_ciphertext=envelope.body_ciphertext[:-1] + b"\x00",
    )
    with tempfile.TemporaryDirectory() as tmp:
        seen = Path(tmp) / "seen.json"
        inbox = LatticeInbox("bob@example.com", keystore=ks, seen_path=seen)
        with pytest.raises(LatticeEnvelopeError):
            inbox.receive(bad)


def test_receive_rejects_envelope_to_wrong_recipient():
    from src.lattice.envelope import LatticeEnvelopeError

    ks, alice, bob = _alice_bob()
    _, carol, _ = _alice_bob()
    # Alice writes to Bob, but Carol tries to open it.
    envelope = make_envelope(alice, bob.public_id, LatticeBody(subject="hi"))
    with tempfile.TemporaryDirectory() as tmp:
        seen = Path(tmp) / "seen.json"
        inbox = LatticeInbox("carol@example.com", keystore=ks, seen_path=seen)
        with pytest.raises(LatticeEnvelopeError):
            inbox.receive(envelope)


def test_receive_rejects_when_account_has_no_identity():
    from src.lattice.envelope import LatticeEnvelopeError

    ks = InMemoryKeystore()
    with tempfile.TemporaryDirectory() as tmp:
        seen = Path(tmp) / "seen.json"
        inbox = LatticeInbox("nobody@example.com", keystore=ks, seen_path=seen)
        with pytest.raises(LatticeEnvelopeError, match="no Lattice identity"):
            from src.lattice.envelope import LatticeEnvelope
            inbox.receive(LatticeEnvelope.__new__(LatticeEnvelope))


def test_seen_file_persists():
    import tempfile
    from pathlib import Path

    ks, alice, bob = _alice_bob()
    envelope = make_envelope(alice, bob.public_id, LatticeBody(subject="hi"))
    with tempfile.TemporaryDirectory() as tmp:
        seen = Path(tmp) / "seen.json"
        inbox = LatticeInbox("bob@example.com", keystore=ks, seen_path=seen)
        inbox.receive(envelope)
        # Re-create the inbox and verify the seen set was reloaded.
        inbox2 = LatticeInbox("bob@example.com", keystore=ks, seen_path=seen)
        _, was_dup = inbox2.receive(envelope)
    assert was_dup is True
