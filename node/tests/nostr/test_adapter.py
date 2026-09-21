"""Tests for the Nostr adapter."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.nostr.adapter import NostrAdapter
from src.nostr.config import NostrConfig
from src.nostr.events import KIND_EMAIL, create_event, verify_event
from src.nostr.identity import generate_nostr_identity
from src.nostr.relay import RelayPool
from src.mail_abstraction.base import Address, MessageSource


def _make_adapter(
    account_id: str = "test@example.com",
    relay_urls: list[str] | None = None,
    data_dir: Path | None = None,
    identity=None,
) -> NostrAdapter:
    """Create a NostrAdapter with in-memory relay pool (no network)."""
    config = NostrConfig(
        relay_urls=relay_urls or [],
    )
    pool = RelayPool(relay_urls=[])
    return NostrAdapter(
        account_id,
        identity=identity,
        config=config,
        relay_pool=pool,
        data_dir=data_dir,
    )


class TestNostrAdapterIdentity:
    def test_ensure_identity_generates_key(self):
        adapter = _make_adapter()
        identity = adapter._ensure_identity()
        assert len(identity.public_key_hex) == 64

    def test_ensure_identity_is_cached(self):
        adapter = _make_adapter()
        id1 = adapter._ensure_identity()
        id2 = adapter._ensure_identity()
        assert id1.public_key_hex == id2.public_key_hex

    def test_set_identity(self):
        adapter = _make_adapter()
        new_id = generate_nostr_identity()
        adapter.set_identity(new_id)
        assert adapter.identity.public_key_hex == new_id.public_key_hex


class TestNostrAdapterFolders:
    def test_list_folders(self):
        adapter = _make_adapter()
        folders = adapter.list_folders()
        assert len(folders) == 1
        assert folders[0].name == "nostr"


class TestNostrAdapterFetch:
    def test_fetch_messages_empty(self, tmp_path):
        adapter = _make_adapter(data_dir=tmp_path)
        msgs = adapter.fetch_messages("nostr")
        assert msgs == []

    def test_fetch_messages_from_file(self, tmp_path):
        adapter = _make_adapter(data_dir=tmp_path)
        mailbox_dir = tmp_path / "etc"
        mailbox_dir.mkdir()
        record = {
            "uid": "test-uid",
            "source": "nostr",
            "sender": "Alice <alice@example.com>",
            "to": ["Bob <bob@example.com>"],
            "subject": "Test",
            "body": "Hello",
            "date": "1700000000",
            "flags": ["\\Seen"],
        }
        mailbox_path = mailbox_dir / "mailbox.test@example.com.jsonl"
        mailbox_path.write_text(json.dumps(record) + "\n")

        msgs = adapter.fetch_messages("nostr")
        assert len(msgs) == 1
        assert msgs[0].subject == "Test"
        assert msgs[0].source == "nostr"


class TestNostrAdapterConnect:
    def test_connect_no_relays(self):
        adapter = _make_adapter()
        ok, msg = adapter.connect()
        assert ok is False
        assert "Nostr relays" in msg

    def test_disconnect(self):
        adapter = _make_adapter()
        ok, msg = adapter.disconnect()
        assert ok is True

    def test_is_connected_default_false(self):
        adapter = _make_adapter()
        assert adapter.is_connected() is False


class TestNostrAdapterSend:
    def test_send_message_requires_recipient(self):
        adapter = _make_adapter()
        with pytest.raises(Exception, match="at least one"):
            adapter.send_message(
                from_address=Address(address="alice@example.com"),
                to_addresses=[],
                subject="Test",
                body="Hello",
            )

    def test_send_message_invalid_recipient(self):
        adapter = _make_adapter()
        ok, msg = adapter.send_message(
            from_address=Address(address="alice@example.com"),
            to_addresses=[Address(address="not-a-hex-key")],
            subject="Test",
            body="Hello",
        )
        assert ok is False
        assert "not a valid" in msg.lower() or "invalid" in msg.lower()

    def test_send_message_wrong_length_pubkey(self):
        adapter = _make_adapter()
        ok, msg = adapter.send_message(
            from_address=Address(address="alice@example.com"),
            to_addresses=[Address(address="aabb")],  # too short
            subject="Test",
            body="Hello",
        )
        assert ok is False


class TestNostrAdapterEventHandling:
    def test_persist_event(self, tmp_path):
        adapter = _make_adapter(data_dir=tmp_path)
        identity = generate_nostr_identity()
        adapter.set_identity(identity)

        event = create_event(
            identity,
            kind=KIND_EMAIL,
            content=json.dumps({
                "subject": "Test",
                "sender": "Alice",
                "to": ["Bob"],
                "body_text": "Hello",
                "sent_at": 1700000000,
            }),
            tags=[["p", identity.public_key_hex]],
        )
        body_data = {
            "subject": "Test",
            "sender": "Alice",
            "to": ["Bob"],
            "body_text": "Hello",
            "sent_at": 1700000000,
        }
        adapter._persist_event(event, body_data)

        mailbox_path = tmp_path / "etc" / "mailbox.test@example.com.jsonl"
        assert mailbox_path.exists()
        lines = [l for l in mailbox_path.read_text().strip().split("\n") if l]
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["subject"] == "Test"
        assert record["source"] == "nostr"
        assert record["nostr_event_id"] == event.id


class TestNostrAdapterMessageSource:
    def test_source_is_nostr(self):
        adapter = _make_adapter()
        assert adapter.source == MessageSource.Nostr
