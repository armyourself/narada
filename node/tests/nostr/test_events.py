"""Tests for Nostr events (NIP-01)."""

from __future__ import annotations

import time

import pytest

from src.nostr.events import (
    KIND_NARADA_EMAIL,
    KIND_TEXT_NOTE,
    NostrEvent,
    NostrFilter,
    create_event,
    verify_event,
    filter_for_dm,
    filter_for_narada_email,
)


def test_create_event(alice_nostr_identity):
    event = create_event(
        alice_nostr_identity,
        kind=KIND_TEXT_NOTE,
        content="Hello, Nostr!",
    )
    assert len(event.id) == 64  # SHA-256 hex
    assert event.pubkey == alice_nostr_identity.public_key_hex
    assert event.kind == KIND_TEXT_NOTE
    assert event.content == "Hello, Nostr!"
    assert len(event.sig) == 128  # 64 bytes hex


def test_verify_event(alice_nostr_identity):
    event = create_event(
        alice_nostr_identity,
        kind=KIND_TEXT_NOTE,
        content="Verify me",
    )
    assert verify_event(event)


def test_verify_event_fails_with_wrong_key(bob_nostr_identity, alice_nostr_identity):
    event = create_event(
        alice_nostr_identity,
        kind=KIND_TEXT_NOTE,
        content="Hello",
    )
    # Tamper with the pubkey
    tampered = NostrEvent(
        id=event.id,
        pubkey=bob_nostr_identity.public_key_hex,
        created_at=event.created_at,
        kind=event.kind,
        tags=event.tags,
        content=event.content,
        sig=event.sig,
    )
    assert not verify_event(tampered)


def test_verify_event_fails_with_tampered_content(alice_nostr_identity):
    event = create_event(
        alice_nostr_identity,
        kind=KIND_TEXT_NOTE,
        content="Original content",
    )
    tampered = NostrEvent(
        id="",
        pubkey=event.pubkey,
        created_at=event.created_at,
        kind=event.kind,
        tags=event.tags,
        content="Tampered content",
        sig=event.sig,
    )
    # Recompute id so verification checks signature against wrong id
    tampered.id = tampered.compute_id()
    assert not verify_event(tampered)


def test_event_serialization_roundtrip(alice_nostr_identity):
    event = create_event(
        alice_nostr_identity,
        kind=KIND_TEXT_NOTE,
        content="Roundtrip test",
    )
    d = event.to_dict()
    restored = NostrEvent.from_dict(d)
    assert restored.id == event.id
    assert restored.pubkey == event.pubkey
    assert restored.kind == event.kind
    assert restored.content == event.content
    assert restored.sig == event.sig


def test_event_json_roundtrip(alice_nostr_identity):
    event = create_event(
        alice_nostr_identity,
        kind=KIND_TEXT_NOTE,
        content="JSON roundtrip",
    )
    json_str = event.to_json()
    restored = NostrEvent.from_json(json_str)
    assert restored.id == event.id
    assert restored.content == event.content


def test_event_tags():
    identity = generate_nostr_identity()
    event = create_event(
        identity,
        kind=KIND_TEXT_NOTE,
        content="Tagged",
        tags=[["p", "abcdef1234567890"], ["e", "deadbeef"]],
    )
    assert len(event.tags) == 2
    assert event.tags[0] == ["p", "abcdef1234567890"]
    assert event.tags[1] == ["e", "deadbeef"]


def test_narada_email_event(alice_nostr_identity):
    event = create_event(
        alice_nostr_identity,
        kind=KIND_NARADA_EMAIL,
        content="encrypted-content-here",
        tags=[["p", "bob-pubkey-hex"]],
    )
    assert event.kind == KIND_NARADA_EMAIL
    assert verify_event(event)


def test_event_id_is_deterministic(alice_nostr_identity):
    """Same content + timestamp = same id."""
    ts = 1700000000
    e1 = create_event(alice_nostr_identity, content="test", created_at=ts)
    e2 = create_event(alice_nostr_identity, content="test", created_at=ts)
    assert e1.id == e2.id


def test_event_id_changes_with_content(alice_nostr_identity):
    ts = 1700000000
    e1 = create_event(alice_nostr_identity, content="one", created_at=ts)
    e2 = create_event(alice_nostr_identity, content="two", created_at=ts)
    assert e1.id != e2.id


def test_filter_to_dict():
    f = NostrFilter(
        authors=["abc123"],
        kinds=[1, 4],
        since=1700000000,
        limit=50,
    )
    d = f.to_dict()
    assert d["authors"] == ["abc123"]
    assert d["kinds"] == [1, 4]
    assert d["since"] == 1700000000
    assert d["limit"] == 50


def test_filter_from_dict():
    d = {
        "authors": ["abc"],
        "kinds": [4],
        "#p": ["def"],
    }
    f = NostrFilter.from_dict(d)
    assert f.authors == ["abc"]
    assert f.kinds == [4]
    assert f.p_tag == ["def"]


def test_filter_for_dm():
    f = filter_for_dm("recipient-hex", sender_pubkey="sender-hex")
    assert f.kinds == [4]
    assert f.p_tag == ["recipient-hex"]
    assert f.authors == ["sender-hex"]


def test_filter_for_narada_email():
    f = filter_for_narada_email("recipient-hex", since=1700000000, limit=100)
    assert f.kinds == [KIND_NARADA_EMAIL]
    assert f.p_tag == ["recipient-hex"]
    assert f.since == 1700000000
    assert f.limit == 100


def test_verify_rejects_bad_id():
    from src.nostr.identity import generate_nostr_identity
    identity = generate_nostr_identity()
    event = create_event(identity, content="test")
    # Tamper with id
    bad_event = NostrEvent(
        id="bad_id",
        pubkey=event.pubkey,
        created_at=event.created_at,
        kind=event.kind,
        tags=event.tags,
        content=event.content,
        sig=event.sig,
    )
    assert not verify_event(bad_event)


def test_verify_rejects_empty_sig():
    from src.nostr.identity import generate_nostr_identity
    identity = generate_nostr_identity()
    event = create_event(identity, content="test")
    bad_event = NostrEvent(
        id=event.id,
        pubkey=event.pubkey,
        created_at=event.created_at,
        kind=event.kind,
        tags=event.tags,
        content=event.content,
        sig="",
    )
    assert not verify_event(bad_event)


def test_verify_rejects_empty_pubkey():
    from src.nostr.identity import generate_nostr_identity
    identity = generate_nostr_identity()
    event = create_event(identity, content="test")
    bad_event = NostrEvent(
        id=event.id,
        pubkey="",
        created_at=event.created_at,
        kind=event.kind,
        tags=event.tags,
        content=event.content,
        sig=event.sig,
    )
    assert not verify_event(bad_event)


# Needed for the test that doesn't use the fixture
from src.nostr.identity import generate_nostr_identity
