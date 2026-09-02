"""Tests for the on-the-wire key-rotation envelope."""

from __future__ import annotations

import json

import pytest

from src.narada.envelope import (
    ENVELOPE_VERSION,
    NaradaEnvelope,
    NaradaEnvelopeError,
    SUPPORTED_ENVELOPE_VERSIONS,
    open_envelope,
)
from src.narada_identity.identity import generate_identity
from src.narada_identity.keystore import InMemoryKeystore
from src.narada.key_update import (
    DEFAULT_OVERLAP_SECONDS,
    KEY_UPDATE_ENVELOPE_VERSION,
    KEY_UPDATE_SENTINEL_SUBJECT,
    KeyUpdateBody,
    KeyUpdateError,
    make_key_update_envelope,
    open_key_update_envelope,
)


@pytest.fixture
def identities():
    ks = InMemoryKeystore()
    alice_old, _ = generate_identity("alice@example.com", keystore=ks)
    alice_new, _ = generate_identity("alice@example.com", keystore=InMemoryKeystore())
    bob, _ = generate_identity("bob@example.com", keystore=InMemoryKeystore())
    return alice_old, alice_new, bob


def test_envelope_version_is_three(identities):
    old, new, bob = identities
    env = make_key_update_envelope(old, bob.public_id, new)
    assert env.v == KEY_UPDATE_ENVELOPE_VERSION
    assert KEY_UPDATE_ENVELOPE_VERSION in SUPPORTED_ENVELOPE_VERSIONS


def test_v1_envelopes_still_work(identities):
    """The regular make_envelope path must still emit v=1."""
    from src.narada.envelope import NaradaBody, make_envelope

    _old, _new, bob = identities
    body = NaradaBody(subject="hi", body_text="hello")
    env = make_envelope(identities[0], bob.public_id, body)
    assert env.v == ENVELOPE_VERSION
    # And the regular open_envelope accepts it.
    opened = open_envelope(env, bob)
    assert opened.subject == "hi"


def test_round_trip_preserves_fields(identities):
    old, new, bob = identities
    env = make_key_update_envelope(old, bob.public_id, new)
    body = open_key_update_envelope(env, bob)
    assert body.prior_public_id == old.public_id
    assert body.new_public_id == new.public_id
    assert body.not_after > 0
    # The default overlap is roughly a week; allow a few seconds slack.
    expected = body.not_after
    assert DEFAULT_OVERLAP_SECONDS - 5 <= expected - int(__import__("time").time()) <= DEFAULT_OVERLAP_SECONDS + 5


def test_sender_signature_uses_old_key(identities):
    """A v=3 envelope's header is signed with the OLD identity's seed.

    If we re-open the envelope and tamper with the body, the
    signature must still fail under the OLD key.
    """
    old, new, bob = identities
    env = make_key_update_envelope(old, bob.public_id, new)
    # Sanity: opens cleanly.
    open_key_update_envelope(env, bob)
    # Construct a tampered envelope with the same signature but
    # a different body ciphertext, and confirm open_envelope
    # (used by open_key_update_envelope) rejects it.
    tampered = NaradaEnvelope(
        v=env.v,
        sender_public_id=env.sender_public_id,
        recipient_public_id=env.recipient_public_id,
        message_id=env.message_id,
        timestamp=env.timestamp,
        nonce=env.nonce,
        signature=env.signature,
        body_ciphertext=b"\x00" * len(env.body_ciphertext),
    )
    with pytest.raises(KeyUpdateError):
        open_key_update_envelope(tampered, bob)


def test_rejects_envelope_addressed_to_different_recipient(identities):
    """The envelope is sealed to one recipient; opening with another fails."""
    old, new, bob = identities
    eve, _ = generate_identity("eve@example.com", keystore=InMemoryKeystore())
    env = make_key_update_envelope(old, bob.public_id, new)
    with pytest.raises(KeyUpdateError):
        open_key_update_envelope(env, eve)


def test_rejects_wrong_envelope_version(identities):
    from src.narada.envelope import NaradaBody, make_envelope

    old, new, bob = identities
    # A regular v=1 envelope is not a key update.
    body = NaradaBody(subject="not a key update")
    v1 = make_envelope(old, bob.public_id, body)
    with pytest.raises(KeyUpdateError):
        open_key_update_envelope(v1, bob)


def test_rejects_same_prior_and_new(identities):
    old, _new_unused, bob = identities
    with pytest.raises(KeyUpdateError):
        make_key_update_envelope(old, bob.public_id, old)


def test_custom_not_after(identities):
    old, new, bob = identities
    env = make_key_update_envelope(old, bob.public_id, new, not_after=1234567890)
    body = open_key_update_envelope(env, bob)
    assert body.not_after == 1234567890


def test_body_to_dict_from_dict_roundtrip():
    body = KeyUpdateBody(
        prior_public_id="narada1aaa",
        new_public_id="narada1bbb",
        not_after=100,
        new_node_id_hint="node1hint",
        issuer_node_id="node1iss",
    )
    d = body.to_dict()
    # JSON-safe round-trip.
    j = json.dumps(d)
    body2 = KeyUpdateBody.from_dict(json.loads(j))
    assert body2 == body


def test_body_from_dict_rejects_bad_version():
    with pytest.raises(KeyUpdateError, match="version"):
        KeyUpdateBody.from_dict(
            {"prior_public_id": "a", "new_public_id": "b", "not_after": 0, "v": 99}
        )


def test_body_from_dict_rejects_missing_fields():
    with pytest.raises(KeyUpdateError, match="missing"):
        KeyUpdateBody.from_dict({"v": 1})


def test_body_from_dict_rejects_wrong_types():
    with pytest.raises(KeyUpdateError):
        KeyUpdateBody.from_dict(
            {
                "prior_public_id": "a",
                "new_public_id": "b",
                "not_after": "not a number",
                "v": 1,
            }
        )


def test_key_update_sentinel_subject_constant():
    """The sentinel is the documented value; tests + tooling rely on it."""
    assert KEY_UPDATE_SENTINEL_SUBJECT == "__narada_key_update__"


def test_issuer_node_id_round_trips(identities):
    old, new, bob = identities
    env = make_key_update_envelope(
        old, bob.public_id, new, issuer_node_id="node1issuer"
    )
    body = open_key_update_envelope(env, bob)
    assert body.issuer_node_id == "node1issuer"


def test_new_node_id_hint_round_trips(identities):
    from src.narada_identity.encoding import (
        IdentityVersion,
        encode_public_id,
    )

    old, _new, bob = identities
    new_hint = encode_public_id(
        b"\x33" * 32, b"\x44" * 32, version=IdentityVersion.V2, node_id_hint="node1hinted"
    )
    env = make_key_update_envelope(
        old, bob.public_id, _new, new_node_id_hint=new_hint
    )
    body = open_key_update_envelope(env, bob)
    assert body.new_node_id_hint == new_hint


def test_key_update_does_not_collide_with_v1_subject(identities):
    """Make sure the sentinel is not a value a user could write
    inadvertently. The recipient's open_key_update_envelope
    refuses to treat a v=1 envelope whose body happens to use
    the same subject as a key update.
    """
    from src.narada.envelope import NaradaBody, make_envelope

    old, new, bob = identities
    body = NaradaBody(
        subject=KEY_UPDATE_SENTINEL_SUBJECT, body_text='{"a": 1}'
    )
    v1 = make_envelope(old, bob.public_id, body)
    # v=1 envelopes are *not* key updates regardless of subject.
    with pytest.raises(KeyUpdateError):
        open_key_update_envelope(v1, bob)


def test_envelope_does_not_have_sender_node_signature(identities):
    """The key-update envelope is a regular Narada envelope; if no
    ``node`` argument is passed, no sender_node_signature is added.
    """
    old, new, bob = identities
    env = make_key_update_envelope(old, bob.public_id, new)
    assert env.sender_node_id is None
    assert env.sender_node_signature is None