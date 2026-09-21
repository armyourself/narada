"""Tests for the relay pool and deduplication."""

from __future__ import annotations

import pytest

from src.nostr.relay import NostrRelay, RelayPool, RelayStatus
from src.nostr.events import NostrEvent, create_event, KIND_TEXT_NOTE
from src.nostr.identity import generate_nostr_identity


class TestRelayStatus:
    def test_default_status(self):
        status = RelayStatus(url="wss://example.com")
        assert status.connected is False
        assert status.reconnect_count == 0


class TestRelayPool:
    def test_create_empty_pool(self):
        pool = RelayPool()
        assert len(pool.relays) == 0

    def test_add_relay(self):
        pool = RelayPool()
        relay = pool.add_relay("wss://relay1.example.com")
        assert len(pool.relays) == 1
        assert relay.url == "wss://relay1.example.com"

    def test_remove_relay(self):
        pool = RelayPool()
        pool.add_relay("wss://relay1.example.com")
        pool.add_relay("wss://relay2.example.com")
        removed = pool.remove_relay("wss://relay1.example.com")
        assert removed is True
        assert len(pool.relays) == 1

    def test_remove_nonexistent_relay(self):
        pool = RelayPool()
        removed = pool.remove_relay("wss://nonexistent.com")
        assert removed is False

    def test_deduplication(self):
        pool = RelayPool()
        assert pool._is_duplicate("event1") is False
        assert pool._is_duplicate("event1") is True
        assert pool._is_duplicate("event2") is False

    def test_clear_dedup_cache(self):
        pool = RelayPool()
        pool._is_duplicate("event1")
        pool.clear_dedup_cache()
        assert pool._is_duplicate("event1") is False

    def test_connected_count(self):
        pool = RelayPool()
        pool.add_relay("wss://relay1.example.com")
        pool.add_relay("wss://relay2.example.com")
        assert pool.connected_count() == 0

    def test_status_summary(self):
        pool = RelayPool()
        pool.add_relay("wss://relay1.example.com")
        pool.add_relay("wss://relay2.example.com")
        statuses = pool.status_summary()
        assert len(statuses) == 2
        assert all(isinstance(s, RelayStatus) for s in statuses)


class TestNostrRelay:
    def test_create_relay(self):
        relay = NostrRelay("wss://example.com")
        assert relay.url == "wss://example.com"
        assert relay.is_connected is False

    def test_create_relay_strips_trailing_slash(self):
        relay = NostrRelay("wss://example.com/")
        assert relay.url == "wss://example.com"
