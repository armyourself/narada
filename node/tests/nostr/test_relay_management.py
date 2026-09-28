"""Tests for runtime relay management: URL validation, config
persistence on the singleton handler, status merging, and the adapter's
pool add/remove paths (all without touching the network)."""

from __future__ import annotations

import pytest

from src.nostr.config import (
    DEFAULT_RELAYS,
    NostrConfig,
    normalize_relay_url,
)
from src.nostr.adapter import NostrAdapter
from src.nostr.relay import RelayPool
from src.internal.nostr_handler import NostrHandler


class TestNormalizeRelayUrl:
    def test_valid_wss(self):
        assert normalize_relay_url("wss://relay.example.com") == "wss://relay.example.com"

    def test_valid_ws(self):
        assert normalize_relay_url("ws://localhost:7777") == "ws://localhost:7777"

    def test_trailing_slash_stripped(self):
        assert normalize_relay_url("wss://relay.example.com/") == "wss://relay.example.com"

    def test_whitespace_stripped(self):
        assert normalize_relay_url("  wss://relay.example.com  ") == "wss://relay.example.com"

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="empty"):
            normalize_relay_url("   ")

    def test_rejects_none_like(self):
        with pytest.raises(ValueError, match="empty"):
            normalize_relay_url("")

    def test_rejects_https(self):
        with pytest.raises(ValueError, match="ws:// or wss://"):
            normalize_relay_url("https://relay.example.com")

    def test_rejects_missing_host(self):
        with pytest.raises(ValueError, match="ws:// or wss://"):
            normalize_relay_url("wss://")

    def test_rejects_embedded_space(self):
        with pytest.raises(ValueError, match="ws:// or wss://"):
            normalize_relay_url("wss://relay example")

    def test_rejects_garbage(self):
        with pytest.raises(ValueError, match="ws:// or wss://"):
            normalize_relay_url("not-a-url")


@pytest.fixture()
def handler(tmp_path, monkeypatch) -> NostrHandler:
    """Isolated singleton: config path redirected to tmp, no adapters."""
    instance = NostrHandler()
    monkeypatch.setattr(instance, "_config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(instance, "_config", None, raising=False)
    instance._adapters.clear()
    yield instance
    instance._config = None
    instance._adapters.clear()


class TestHandlerRelayConfig:
    def test_add_persists_to_config_file(self, handler, tmp_path):
        ok, msg = handler.add_relay("wss://new.example.com")
        assert ok, msg
        path = tmp_path / "config.json"
        assert path.exists()
        saved = NostrConfig.from_file(path)
        assert "wss://new.example.com" in saved.relay_urls
        # defaults ride along until the user edits them
        for url in DEFAULT_RELAYS:
            assert url in saved.relay_urls

    def test_get_config_caches_loaded_file(self, handler, tmp_path):
        handler.add_relay("wss://new.example.com")
        # same instance, no re-read surprises
        assert handler.get_config() is handler.get_config()
        assert "wss://new.example.com" in handler.get_config().relay_urls

    def test_duplicate_relay_rejected_case_insensitive(self, handler):
        ok, _ = handler.add_relay("wss://new.example.com")
        assert ok
        ok2, msg2 = handler.add_relay("WSS://NEW.example.com/")
        assert not ok2
        assert "already" in msg2.lower()

    def test_invalid_url_rejected_and_not_persisted(self, handler, tmp_path):
        ok, msg = handler.add_relay("https://relay.example.com")
        assert not ok
        assert "ws:// or wss://" in msg
        assert not (tmp_path / "config.json").exists()

    def test_remove_persists(self, handler, tmp_path):
        handler.add_relay("wss://new.example.com")
        ok, msg = handler.remove_relay("wss://new.example.com")
        assert ok, msg
        saved = NostrConfig.from_file(tmp_path / "config.json")
        assert "wss://new.example.com" not in saved.relay_urls

    def test_remove_normalizes_trailing_slash(self, handler, tmp_path):
        handler.add_relay("wss://new.example.com/")
        ok, _ = handler.remove_relay("wss://new.example.com")
        assert ok
        assert "wss://new.example.com" not in NostrConfig.from_file(
            tmp_path / "config.json"
        ).relay_urls

    def test_remove_unknown_relay_fails(self, handler):
        ok, msg = handler.remove_relay("wss://nope.example.com")
        assert not ok
        assert "not configured" in msg

    def test_cannot_remove_last_relay(self, handler):
        handler._config = NostrConfig(relay_urls=["wss://only.example.com"])
        ok, msg = handler.remove_relay("wss://only.example.com")
        assert not ok
        assert "last configured relay" in msg
        assert "wss://only.example.com" in handler.get_config().relay_urls

    def test_status_includes_configured_but_unconnected_relays(self, handler):
        handler._config = NostrConfig(relay_urls=["wss://pending.example.com"])
        statuses = handler.get_relay_status()
        match = [s for s in statuses if s["url"] == "wss://pending.example.com"]
        assert match, "configured relay missing from status"
        assert match[0]["connected"] is False
        assert match[0]["reconnect_count"] == 0


def _make_adapter(data_dir=None) -> NostrAdapter:
    config = NostrConfig(relay_urls=[])
    pool = RelayPool(relay_urls=[])
    return NostrAdapter(
        "test@example.com",
        identity=None,
        config=config,
        relay_pool=pool,
        data_dir=data_dir,
    )


class TestAdapterPoolManagement:
    def test_add_relay_duplicate_never_connects(self, tmp_path):
        adapter = _make_adapter(data_dir=tmp_path)
        adapter.relay_pool.add_relay("wss://dup.example.com")
        # duplicate check runs before any socket work — offline-safe
        ok, msg = adapter.add_relay("wss://dup.example.com/")
        assert not ok
        assert "already in pool" in msg
        assert len(adapter.relay_pool.relays) == 1

    def test_remove_relay_disconnects_then_unlists(self, tmp_path):
        adapter = _make_adapter(data_dir=tmp_path)
        relay = adapter.relay_pool.add_relay("wss://drop.example.com")
        ok, msg = adapter.remove_relay("wss://drop.example.com")
        assert ok, msg
        assert not adapter.relay_pool.relays
        # listener must be stopped so it cannot auto-reconnect forever
        assert relay._closing or relay._listener is None

    def test_remove_relay_trailing_slash_match(self, tmp_path):
        adapter = _make_adapter(data_dir=tmp_path)
        adapter.relay_pool.add_relay("wss://drop.example.com")
        ok, _ = adapter.remove_relay("wss://drop.example.com/")
        assert ok
        assert not adapter.relay_pool.relays

    def test_remove_relay_not_in_pool(self, tmp_path):
        adapter = _make_adapter(data_dir=tmp_path)
        ok, msg = adapter.remove_relay("wss://ghost.example.com")
        assert not ok
        assert "not in pool" in msg
