"""Tests for Nostr configuration."""

from __future__ import annotations

import json
import os

import pytest

from src.nostr.config import NostrConfig, DEFAULT_RELAYS, NARADA_EMAIL_KIND


def test_default_config():
    config = NostrConfig()
    assert config.transport == "nostr"
    assert config.relay_urls == list(DEFAULT_RELAYS)
    assert config.encryption == "nip04"
    assert config.event_kind == NARADA_EMAIL_KIND


def test_config_to_dict():
    config = NostrConfig(transport="legacy_narada")
    d = config.to_dict()
    assert d["transport"] == "legacy_narada"
    assert "relay_urls" in d


def test_config_from_dict():
    d = {"transport": "smtp", "relay_urls": ["wss://relay1.com"]}
    config = NostrConfig.from_dict(d)
    assert config.transport == "smtp"
    assert config.relay_urls == ["wss://relay1.com"]


def test_config_roundtrip():
    config = NostrConfig(transport="nostr", encryption="nip44")
    d = config.to_dict()
    restored = NostrConfig.from_dict(d)
    assert restored.transport == config.transport
    assert restored.encryption == config.encryption


def test_config_from_file(tmp_path):
    config = NostrConfig(transport="smtp")
    path = tmp_path / "nostr_config.json"
    config.save(path)
    loaded = NostrConfig.from_file(path)
    assert loaded.transport == "smtp"


def test_config_from_file_missing():
    config = NostrConfig.from_file("/nonexistent/path/config.json")
    assert config.transport == "nostr"  # falls back to default


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("NARADA_TRANSPORT", "legacy_narada")
    monkeypatch.setenv("NARADA_NOSTR_RELAYS", "wss://a.com,wss://b.com")
    monkeypatch.setenv("NARADA_NOSTR_ENCRYPTION", "nip44")

    config = NostrConfig.from_env()
    assert config.transport == "legacy_narada"
    assert config.relay_urls == ["wss://a.com", "wss://b.com"]
    assert config.encryption == "nip44"


def test_config_from_env_defaults(monkeypatch):
    monkeypatch.delenv("NARADA_TRANSPORT", raising=False)
    monkeypatch.delenv("NARADA_NOSTR_RELAYS", raising=False)
    monkeypatch.delenv("NARADA_NOSTR_ENCRYPTION", raising=False)

    config = NostrConfig.from_env()
    assert config.transport == "nostr"
    assert config.relay_urls == list(DEFAULT_RELAYS)
