"""Tests for kind-0 profile publishing and relay status fidelity.

Everything runs offline: the profile event is verified by signature, the
publish path uses an empty relay pool (no sockets), and the reconnect
counters are exercised with a stubbed websockets module.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types

import pytest

from src.nostr.adapter import NostrAdapter
from src.nostr.config import NostrConfig
from src.nostr.events import KIND_META, verify_event
from src.nostr.relay import NostrRelay, RelayPool


def _make_adapter(account_id: str = "test@example.com") -> NostrAdapter:
    """Adapter with an in-memory pool (no network) and no relays."""
    return NostrAdapter(
        account_id,
        identity=None,
        config=NostrConfig(relay_urls=[]),
        relay_pool=RelayPool(relay_urls=[]),
    )


class TestBuildProfileEvent:
    def test_kind_is_zero(self):
        event = _make_adapter().build_profile_event({"name": "Zombelius"})
        assert event.kind == KIND_META == 0

    def test_content_is_json_of_profile(self):
        profile = {"name": "Zombelius", "about": "alpha tester"}
        event = _make_adapter().build_profile_event(profile)
        assert json.loads(event.content) == profile

    def test_event_verifies(self):
        event = _make_adapter().build_profile_event({"name": "Zombelius"})
        assert verify_event(event)

    def test_event_targets_no_kinds_tag(self):
        """NIP-01 kind 0 carries no `k` tag; profile events are bare."""
        event = _make_adapter().build_profile_event({"name": "Zombelius"})
        assert event.tags == []

    def test_unicode_profile_survives(self):
        profile = {"name": "é测试", "about": "emoji 🚀"}
        event = _make_adapter().build_profile_event(profile)
        assert json.loads(event.content) == profile

    def test_identity_created_lazily(self):
        adapter = _make_adapter()
        assert adapter.identity is None
        adapter.build_profile_event({"name": "x"})
        assert adapter.identity is not None


class TestPublishProfile:
    def test_empty_profile_rejected_before_io(self):
        ok, msg = _make_adapter().publish_profile({})
        assert not ok
        assert "empty" in msg.lower()

    def test_no_relays_reports_failure(self):
        """Empty pool: failover has nowhere to publish — no network, no hang."""
        adapter = _make_adapter()
        ok, msg = adapter.publish_profile({"name": "Zombelius"})
        assert not ok
        assert "Profile publish failed" in msg

    def test_relay_pool_publish_failure_is_reported(self, monkeypatch):
        adapter = _make_adapter()

        async def _fail(event):
            return False, "All relays failed"

        monkeypatch.setattr(adapter.relay_pool, "publish_with_failover", _fail)
        ok, msg = adapter.publish_profile({"name": "Zombelius"})
        assert not ok
        assert "All relays failed" in msg

    def test_success_message_contains_event_id(self, monkeypatch):
        adapter = _make_adapter()
        captured = {}

        async def _ok(event):
            captured["event"] = event
            return True, "published"

        monkeypatch.setattr(adapter.relay_pool, "publish_with_failover", _ok)
        ok, msg = adapter.publish_profile({"name": "Zombelius"})
        assert ok
        assert captured["event"].id[:12] in msg
        assert verify_event(captured["event"])

    def test_publish_exception_is_contained(self, monkeypatch):
        adapter = _make_adapter()

        async def _boom(event):
            raise RuntimeError("socket exploded")

        monkeypatch.setattr(adapter.relay_pool, "publish_with_failover", _boom)
        ok, msg = adapter.publish_profile({"name": "Zombelius"})
        assert not ok
        assert "socket exploded" in msg


class TestStatusEndpoint:
    def _store(self, handler, account: str):
        from src.nostr.identity import generate_nostr_identity

        identity = generate_nostr_identity()
        adapter = handler.store_identity(
            account,
            identity.public_key_bech32,
            identity.secret_key_hex,
            config=NostrConfig(relay_urls=[]),
        )
        return identity, adapter

    @pytest.fixture()
    def handler(self, tmp_path, monkeypatch):
        from src.internal.nostr_handler import NostrHandler

        instance = NostrHandler()
        monkeypatch.setattr(instance, "_config_path", lambda: tmp_path / "config.json")
        monkeypatch.setattr(instance, "_config", None, raising=False)
        instance._adapters.clear()
        yield instance
        instance._adapters.clear()
        instance._config = None

    def test_status_reports_identity_and_subscription(self, handler, monkeypatch):
        import src.routers.nostr_tasks as nostr_tasks

        _, adapter = self._store(handler, "alice@example.com")
        monkeypatch.setattr(nostr_tasks, "nostr_handler", handler)

        response = asyncio.run(nostr_tasks.nostr_status("alice@example.com"))
        assert response.success
        data = response.data
        assert data["npub"] == adapter.identity.public_key_bech32
        assert data["subscribed"] is False
        assert data["relays"] == []
        assert data["relays_total"] == 0

    def test_status_unknown_account_fails(self, handler, monkeypatch):
        import src.routers.nostr_tasks as nostr_tasks

        monkeypatch.setattr(nostr_tasks, "nostr_handler", handler)
        response = asyncio.run(nostr_tasks.nostr_status("ghost@example.com"))
        assert response.success is False

    def test_publish_profile_endpoint_rejects_missing_identity(
        self, handler, monkeypatch
    ):
        import src.routers.nostr_tasks as nostr_tasks
        from src.routers.nostr_tasks import PublishProfileRequest

        monkeypatch.setattr(nostr_tasks, "nostr_handler", handler)
        request = PublishProfileRequest(account="ghost@example.com", name="Ghost")
        response = asyncio.run(nostr_tasks.publish_profile(request))
        assert response.success is False
        assert "No Nostr identity" in response.message

    def test_publish_profile_endpoint_rejects_empty_profile(
        self, handler, monkeypatch
    ):
        import src.routers.nostr_tasks as nostr_tasks
        from src.routers.nostr_tasks import PublishProfileRequest

        self._store(handler, "alice@example.com")
        monkeypatch.setattr(nostr_tasks, "nostr_handler", handler)
        request = PublishProfileRequest(account="alice@example.com")
        response = asyncio.run(nostr_tasks.publish_profile(request))
        assert response.success is False
        assert "empty" in response.message.lower()

    def test_publish_profile_endpoint_returns_profile_on_success(
        self, handler, monkeypatch
    ):
        import src.routers.nostr_tasks as nostr_tasks
        from src.routers.nostr_tasks import PublishProfileRequest

        _, adapter = self._store(handler, "alice@example.com")
        monkeypatch.setattr(nostr_tasks, "nostr_handler", handler)
        monkeypatch.setattr(
            adapter, "publish_profile", lambda profile: (True, "Profile published")
        )
        request = PublishProfileRequest(
            account="alice@example.com", name="Alice", about="hi"
        )
        response = asyncio.run(nostr_tasks.publish_profile(request))
        assert response.success
        assert response.data["profile"] == {"name": "Alice", "about": "hi"}

    def test_publish_profile_endpoint_strips_unset_fields(
        self, handler, monkeypatch
    ):
        import src.routers.nostr_tasks as nostr_tasks
        from src.routers.nostr_tasks import PublishProfileRequest

        _, adapter = self._store(handler, "alice@example.com")
        monkeypatch.setattr(nostr_tasks, "nostr_handler", handler)
        monkeypatch.setattr(
            adapter, "publish_profile", lambda profile: (True, "ok")
        )
        request = PublishProfileRequest(account="alice@example.com", name="Alice")
        response = asyncio.run(nostr_tasks.publish_profile(request))
        assert set(response.data["profile"]) == {"name"}


class TestReconnectFidelity:
    """`reconnect_count` is telemetry: it must survive a successful
    connect, while the exponential backoff uses its own counter."""

    @pytest.fixture()
    def relay(self) -> NostrRelay:
        return NostrRelay("wss://relay.example.com")

    def test_connect_success_does_not_reset_reconnect_count(
        self, relay, monkeypatch
    ):
        fake = types.ModuleType("websockets")

        async def _fake_connect(url, **kwargs):
            return object()

        fake.connect = _fake_connect
        monkeypatch.setitem(sys.modules, "websockets", fake)
        monkeypatch.setattr(relay, "_start_listener", lambda: None)

        async def _no_resubscribe():
            return None

        monkeypatch.setattr(relay, "_resubscribe_all", _no_resubscribe)

        relay._status.reconnect_count = 7
        assert asyncio.run(relay.connect()) is True
        assert relay._status.reconnect_count == 7
        assert relay._backoff_attempt == 0

    def test_reconnect_backoff_starts_fresh_and_counts_up(
        self, relay, monkeypatch
    ):
        delays: list[float] = []

        async def _sleep(delay):
            delays.append(delay)

        async def _connect():
            return True

        monkeypatch.setattr(asyncio, "sleep", _sleep)
        monkeypatch.setattr(relay, "connect", _connect)

        relay._status.reconnect_count = 5  # prior history
        assert asyncio.run(relay.reconnect()) is True
        assert delays == [1.0]  # fresh backoff, not 2**5
        assert relay._status.reconnect_count == 6
        assert relay._backoff_attempt == 1

        assert asyncio.run(relay.reconnect()) is True
        assert delays == [1.0, 2.0]
        assert relay._status.reconnect_count == 7
        assert relay._backoff_attempt == 2

    def test_backoff_is_capped(self, relay, monkeypatch):
        delays: list[float] = []

        async def _sleep(delay):
            delays.append(delay)

        async def _connect():
            return True

        monkeypatch.setattr(asyncio, "sleep", _sleep)
        monkeypatch.setattr(relay, "connect", _connect)

        relay._backoff_attempt = 30
        asyncio.run(relay.reconnect())
        assert delays == [relay._max_reconnect_delay]
