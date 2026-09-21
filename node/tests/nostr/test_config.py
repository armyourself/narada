"""Tests for Nostr configuration."""

from __future__ import annotations

import json
import os

import pytest

from src.nostr.config import NostrConfig, DEFAULT_RELAYS, EMAIL_KIND


def test_default_config():
    config = NostrConfig()
    assert config.relay_urls == list(DEFAULT_RELAYS)
    assert config.encryption == "nip04"
    assert config.event_kind == EMAIL_KIND


def test_config_to_dict():
    config = NostrConfig(encryption="nip44")
    d = config.to_dict()
    assert d["encryption"] == "nip44"
    assert "relay_urls" in d


def test_config_from_dict():
    d = {"relay_urls": ["wss://relay1.com"], "encryption": "nip44"}
    config = NostrConfig.from_dict(d)
    assert config.relay_urls == ["wss://relay1.com"]
    assert config.encryption == "nip44"


def test_config_roundtrip():
    config = NostrConfig(encryption="nip44")
    d = config.to_dict()
    restored = NostrConfig.from_dict(d)
    assert restored.encryption == config.encryption


def test_config_from_file(tmp_path):
    config = NostrConfig(encryption="nip44")
    path = tmp_path / "nostr_config.json"
    config.save(path)
    loaded = NostrConfig.from_file(path)
    assert loaded.encryption == "nip44"


def test_config_from_file_missing():
    config = NostrConfig.from_file("/nonexistent/path/config.json")
    assert config.relay_urls == list(DEFAULT_RELAYS)  # falls back to default


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("NOSTR_RELAYS", "wss://a.com,wss://b.com")
    monkeypatch.setenv("NOSTR_ENCRYPTION", "nip44")

    config = NostrConfig.from_env()
    assert config.relay_urls == ["wss://a.com", "wss://b.com"]
    assert config.encryption == "nip44"


def test_config_from_env_defaults(monkeypatch):
    monkeypatch.delenv("NOSTR_RELAYS", raising=False)
    monkeypatch.delenv("NOSTR_ENCRYPTION", raising=False)

    config = NostrConfig.from_env()
    assert config.relay_urls == list(DEFAULT_RELAYS)
