"""Tests for Nostr identity lifecycle: store/load/delete round-trips and
the resurrect fix (deleting an identity must remove the persisted key
file, not just the live adapter)."""

from __future__ import annotations

import json

import pytest

from src.internal.nostr_handler import NostrHandler
from src.nostr.config import NostrConfig
from src.nostr.identity import generate_nostr_identity


@pytest.fixture()
def handler(tmp_path, monkeypatch) -> NostrHandler:
    """Isolated singleton: identity dir redirected to tmp, no adapters."""
    instance = NostrHandler()
    etc = tmp_path / "etc"
    monkeypatch.setattr(instance, "_identity_dir", lambda: etc)
    monkeypatch.setattr(instance, "_config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(instance, "_config", None, raising=False)
    instance._adapters.clear()
    yield instance
    instance._adapters.clear()
    instance._config = None


def _store(handler: NostrHandler, account: str):
    identity = generate_nostr_identity()
    adapter = handler.store_identity(
        account,
        identity.public_key_bech32,
        identity.secret_key_hex,
        config=NostrConfig(relay_urls=[]),
    )
    return identity, adapter


class TestStoreAndDelete:
    def test_store_persists_key_file(self, handler):
        identity, _ = _store(handler, "alice@example.com")
        path = handler._identity_path("alice@example.com")
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["npub"] == identity.public_key_bech32
        assert data["nsec_hex"] == identity.secret_key_hex

    def test_delete_removes_adapter_and_file(self, handler):
        _, adapter = _store(handler, "alice@example.com")
        path = handler._identity_path("alice@example.com")
        assert handler.get_adapter("alice@example.com") is adapter

        ok, msg = handler.delete_identity("alice@example.com")
        assert ok, msg
        assert not path.exists()
        assert handler.get_adapter("alice@example.com") is None
        assert "alice@example.com" not in handler.get_all_adapters()

    def test_delete_disconnects_adapter(self, handler, monkeypatch):
        _, adapter = _store(handler, "alice@example.com")
        called = {"n": 0}
        monkeypatch.setattr(adapter, "disconnect", lambda: (called.__setitem__("n", called["n"] + 1), (True, "ok"))[1])

        ok, _ = handler.delete_identity("alice@example.com")
        assert ok
        assert called["n"] == 1

    def test_delete_unknown_account_fails(self, handler):
        ok, msg = handler.delete_identity("ghost@example.com")
        assert not ok
        assert "No Nostr identity" in msg

    def test_delete_survives_disconnect_error(self, handler, monkeypatch):
        _, adapter = _store(handler, "alice@example.com")

        def _boom():
            raise RuntimeError("socket already closed")

        monkeypatch.setattr(adapter, "disconnect", _boom)
        ok, msg = handler.delete_identity("alice@example.com")
        assert ok, msg
        assert handler.get_adapter("alice@example.com") is None
        assert not handler._identity_path("alice@example.com").exists()

    def test_deleted_identity_does_not_resurrect_on_reload(self, handler):
        _store(handler, "alice@example.com")
        handler.delete_identity("alice@example.com")

        handler._adapters.clear()
        loaded = handler.load_stored_identities(NostrConfig(relay_urls=[]))
        assert loaded == {}
        assert handler.get_adapter("alice@example.com") is None

    def test_reload_restores_untouched_identity(self, handler):
        identity, _ = _store(handler, "alice@example.com")
        handler._adapters.clear()

        loaded = handler.load_stored_identities(NostrConfig(relay_urls=[]))
        assert "alice@example.com" in loaded
        assert loaded["alice@example.com"].identity.public_key_bech32 == (
            identity.public_key_bech32
        )


class TestFilenameParsing:
    def test_dotted_account_id_round_trips(self, handler):
        """`user.name@example.com` must not reload as `name@example.com`."""
        identity, _ = _store(handler, "user.name@example.com")
        handler._adapters.clear()

        loaded = handler.load_stored_identities(NostrConfig(relay_urls=[]))
        assert "user.name@example.com" in loaded
        assert loaded["user.name@example.com"].identity.public_key_bech32 == (
            identity.public_key_bech32
        )
        # the old split(".", 2) parser leaked a bogus short key
        assert "name@example.com" not in loaded

    def test_delete_dotted_account(self, handler):
        _store(handler, "user.name@example.com")
        ok, msg = handler.delete_identity("user.name@example.com")
        assert ok, msg
        assert not handler._identity_path("user.name@example.com").exists()


class TestDeleteEndpoint:
    def test_endpoint_reports_success(self, handler, monkeypatch):
        import src.routers.nostr_tasks as nostr_tasks

        _store(handler, "alice@example.com")
        monkeypatch.setattr(nostr_tasks, "nostr_handler", handler)

        import asyncio

        response = asyncio.run(nostr_tasks.delete_identity("alice@example.com"))
        assert response.success is True
        assert handler.get_adapter("alice@example.com") is None

    def test_endpoint_reports_missing_identity(self, handler, monkeypatch):
        import src.routers.nostr_tasks as nostr_tasks

        monkeypatch.setattr(nostr_tasks, "nostr_handler", handler)

        import asyncio

        response = asyncio.run(nostr_tasks.delete_identity("ghost@example.com"))
        assert response.success is False
        assert "No Nostr identity" in response.message
