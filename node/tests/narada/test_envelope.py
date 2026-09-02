"""Tests for the narada envelope (seal/open)."""

from __future__ import annotations

import time

import pytest

from src.narada.envelope import (
    ENVELOPE_VERSION,
    NaradaBody,
    NaradaEnvelope,
    NaradaEnvelopeError,
    make_envelope,
    open_envelope,
)


def _alice_to_bob_body() -> NaradaBody:
    return NaradaBody(
        subject="hi bob",
        sender="Alice <alice@example.com>",
        to=("Bob <bob@example.com>",),
        cc=(),
        body_text="hello there",
        sent_at=1700000000,
    )


def test_seal_open_roundtrip(alice_identity, bob_identity):
    body = _alice_to_bob_body()
    envelope = make_envelope(alice_identity, bob_identity.public_id, body)
    assert envelope.v == ENVELOPE_VERSION
    assert envelope.sender_public_id == alice_identity.public_id
    assert envelope.recipient_public_id == bob_identity.public_id
    assert len(envelope.nonce) == 16
    assert len(envelope.signature) == 64

    opened = open_envelope(envelope, bob_identity)
    assert opened.subject == body.subject
    assert opened.sender == body.sender
    assert opened.to == body.to
    assert opened.body_text == body.body_text
    assert opened.sent_at == body.sent_at


def test_open_rejects_wrong_recipient(alice_identity, bob_identity):
    body = _alice_to_bob_body()
    envelope = make_envelope(alice_identity, bob_identity.public_id, body)
    with pytest.raises(NaradaEnvelopeError, match="different recipient"):
        open_envelope(envelope, alice_identity)


def test_open_rejects_tampered_ciphertext(alice_identity, bob_identity):
    envelope = make_envelope(alice_identity, bob_identity.public_id, _alice_to_bob_body())
    tampered = NaradaEnvelope(
        v=envelope.v,
        sender_public_id=envelope.sender_public_id,
        recipient_public_id=envelope.recipient_public_id,
        message_id=envelope.message_id,
        timestamp=envelope.timestamp,
        nonce=envelope.nonce,
        signature=envelope.signature,
        body_ciphertext=envelope.body_ciphertext[:-1] + b"\x00",
    )
    with pytest.raises(NaradaEnvelopeError, match="ciphertext"):
        open_envelope(tampered, bob_identity)


def test_open_rejects_tampered_signature(alice_identity, bob_identity):
    envelope = make_envelope(alice_identity, bob_identity.public_id, _alice_to_bob_body())
    bad_sig = b"\x00" * 64
    tampered = NaradaEnvelope(
        v=envelope.v,
        sender_public_id=envelope.sender_public_id,
        recipient_public_id=envelope.recipient_public_id,
        message_id=envelope.message_id,
        timestamp=envelope.timestamp,
        nonce=envelope.nonce,
        signature=bad_sig,
        body_ciphertext=envelope.body_ciphertext,
    )
    with pytest.raises(NaradaEnvelopeError, match="signature"):
        open_envelope(tampered, bob_identity)


def test_open_rejects_tampered_message_id(alice_identity, bob_identity):
    envelope = make_envelope(alice_identity, bob_identity.public_id, _alice_to_bob_body())
    tampered = NaradaEnvelope(
        v=envelope.v,
        sender_public_id=envelope.sender_public_id,
        recipient_public_id=envelope.recipient_public_id,
        message_id="attacker-substituted-id",
        timestamp=envelope.timestamp,
        nonce=envelope.nonce,
        signature=envelope.signature,
        body_ciphertext=envelope.body_ciphertext,
    )
    with pytest.raises(NaradaEnvelopeError):
        open_envelope(tampered, bob_identity)


def test_open_rejects_old_timestamp(alice_identity, bob_identity):
    old = int(time.time()) - 3600
    envelope = make_envelope(
        alice_identity, bob_identity.public_id, _alice_to_bob_body(), timestamp=old
    )
    with pytest.raises(NaradaEnvelopeError, match="timestamp"):
        open_envelope(envelope, bob_identity)


def test_open_rejects_unsupported_version(alice_identity, bob_identity):
    envelope = make_envelope(alice_identity, bob_identity.public_id, _alice_to_bob_body())
    bad = NaradaEnvelope(
        v=99,
        sender_public_id=envelope.sender_public_id,
        recipient_public_id=envelope.recipient_public_id,
        message_id=envelope.message_id,
        timestamp=envelope.timestamp,
        nonce=envelope.nonce,
        signature=envelope.signature,
        body_ciphertext=envelope.body_ciphertext,
    )
    with pytest.raises(NaradaEnvelopeError, match="version"):
        open_envelope(bad, bob_identity)


def test_open_rejects_invalid_sender_public_id(alice_identity, bob_identity):
    envelope = make_envelope(alice_identity, bob_identity.public_id, _alice_to_bob_body())
    bad = NaradaEnvelope(
        v=envelope.v,
        sender_public_id="not-a-narada-id",
        recipient_public_id=envelope.recipient_public_id,
        message_id=envelope.message_id,
        timestamp=envelope.timestamp,
        nonce=envelope.nonce,
        signature=envelope.signature,
        body_ciphertext=envelope.body_ciphertext,
    )
    with pytest.raises(NaradaEnvelopeError):
        open_envelope(bad, bob_identity)


def test_make_envelope_rejects_invalid_recipient(alice_identity):
    with pytest.raises(NaradaEnvelopeError, match="recipient public id"):
        make_envelope(alice_identity, "not-a-narada-id", _alice_to_bob_body())


def test_envelope_serialization_roundtrip(alice_identity, bob_identity):
    envelope = make_envelope(alice_identity, bob_identity.public_id, _alice_to_bob_body())
    d = envelope.as_dict()
    assert d["v"] == ENVELOPE_VERSION
    assert d["sender_public_id"] == alice_identity.public_id
    # nonce/signature/ciphertext must be base64 strings, not raw bytes
    assert isinstance(d["nonce"], str)
    assert isinstance(d["signature"], str)
    assert isinstance(d["body_ciphertext"], str)
    back = NaradaEnvelope.from_dict(d)
    assert back == envelope


def test_from_dict_rejects_missing_field(alice_identity, bob_identity):
    envelope = make_envelope(alice_identity, bob_identity.public_id, _alice_to_bob_body())
    d = envelope.as_dict()
    del d["body_ciphertext"]
    with pytest.raises(NaradaEnvelopeError, match="body_ciphertext"):
        NaradaEnvelope.from_dict(d)


def test_from_dict_rejects_bad_base64(alice_identity, bob_identity):
    envelope = make_envelope(alice_identity, bob_identity.public_id, _alice_to_bob_body())
    d = envelope.as_dict()
    d["nonce"] = "not!base64!"
    with pytest.raises(NaradaEnvelopeError):
        NaradaEnvelope.from_dict(d)


def test_nonce_is_random_per_envelope(alice_identity, bob_identity):
    # Two envelopes with the same body but different timestamps should
    # have different nonces (we use a fresh message_id each time too).
    env1 = make_envelope(alice_identity, bob_identity.public_id, _alice_to_bob_body())
    env2 = make_envelope(alice_identity, bob_identity.public_id, _alice_to_bob_body())
    assert env1.nonce != env2.nonce
    assert env1.message_id != env2.message_id
