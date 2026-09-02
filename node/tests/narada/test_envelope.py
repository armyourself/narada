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


# --- Node-identity envelope fields ----------------------------------------


def test_envelope_with_node_identity_roundtrip(alice_identity, bob_identity):
    from src.narada.node_identity import NaradaNodeIdentity

    node = NaradaNodeIdentity.generate()
    envelope = make_envelope(
        alice_identity,
        bob_identity.public_id,
        _alice_to_bob_body(),
        node=node,
    )
    assert envelope.sender_node_id == node.public_id
    assert envelope.sender_node_signature is not None
    assert len(envelope.sender_node_signature) == 64
    # open_envelope verifies the node signature implicitly.
    opened = open_envelope(envelope, bob_identity)
    assert opened.subject == "hi bob"


def test_envelope_node_id_serialized_in_dict(alice_identity, bob_identity):
    from src.narada.node_identity import NaradaNodeIdentity

    node = NaradaNodeIdentity.generate()
    envelope = make_envelope(
        alice_identity,
        bob_identity.public_id,
        _alice_to_bob_body(),
        node=node,
    )
    d = envelope.as_dict()
    assert d["sender_node_id"] == node.public_id
    # The node signature must round-trip through JSON.
    reloaded = NaradaEnvelope.from_dict(d)
    assert reloaded.sender_node_id == node.public_id
    assert reloaded.sender_node_signature == envelope.sender_node_signature


def test_envelope_node_signature_is_bound_to_envelope(alice_identity, bob_identity):
    """A node signature must not be valid for a different envelope."""
    from src.narada.node_identity import NaradaNodeIdentity

    node = NaradaNodeIdentity.generate()
    env1 = make_envelope(
        alice_identity,
        bob_identity.public_id,
        _alice_to_bob_body(),
        node=node,
    )
    # A second, fresh envelope must reject the first envelope's node
    # signature, because the node signed env1's header bytes (which
    # include env1's nonce and timestamp).
    env2 = make_envelope(
        alice_identity,
        bob_identity.public_id,
        _alice_to_bob_body(),
        node=node,
    )
    # Re-attach env1's node signature to env2's payload.
    tampered = NaradaEnvelope(
        v=env2.v,
        sender_public_id=env2.sender_public_id,
        recipient_public_id=env2.recipient_public_id,
        message_id=env2.message_id,
        timestamp=env2.timestamp,
        nonce=env2.nonce,
        signature=env2.signature,
        body_ciphertext=env2.body_ciphertext,
        sender_node_id=env1.sender_node_id,
        sender_node_signature=env1.sender_node_signature,
    )
    with pytest.raises(NaradaEnvelopeError, match="node signature"):
        open_envelope(tampered, bob_identity)


def test_envelope_rejects_mismatched_node_fields(alice_identity, bob_identity):
    from src.narada.envelope import NaradaEnvelope, NaradaEnvelopeError

    envelope = make_envelope(alice_identity, bob_identity.public_id, _alice_to_bob_body())
    bad = NaradaEnvelope(
        v=envelope.v,
        sender_public_id=envelope.sender_public_id,
        recipient_public_id=envelope.recipient_public_id,
        message_id=envelope.message_id,
        timestamp=envelope.timestamp,
        nonce=envelope.nonce,
        signature=envelope.signature,
        body_ciphertext=envelope.body_ciphertext,
        sender_node_id="node1qqqq",
        sender_node_signature=None,
    )
    with pytest.raises(NaradaEnvelopeError, match="one of sender_node"):
        open_envelope(bad, bob_identity)


def test_envelope_without_node_fields_still_opens(alice_identity, bob_identity):
    """Backward compatibility: an envelope with no node fields must still work."""
    envelope = make_envelope(alice_identity, bob_identity.public_id, _alice_to_bob_body())
    assert envelope.sender_node_id is None
    assert envelope.sender_node_signature is None
    opened = open_envelope(envelope, bob_identity)
    assert opened.subject == "hi bob"
