"""Tests for the narada directory (local + in-memory)."""

from __future__ import annotations

import json

import pytest

from src.narada.directory import (
    InMemoryDirectory,
    NaradaDirectory,
    LocalContactList,
)


PUBLIC_ID_A = "narada1aaa"
PUBLIC_ID_B = "narada1bbb"


def test_in_memory_directory_add_lookup_remove():
    d = InMemoryDirectory()
    assert d.lookup(PUBLIC_ID_A) is None
    d.add(PUBLIC_ID_A, "http://127.0.0.1:8001", "alice@example.com")
    assert d.lookup(PUBLIC_ID_A) == "http://127.0.0.1:8001"
    assert d.remove(PUBLIC_ID_A) is True
    assert d.lookup(PUBLIC_ID_A) is None


def test_in_memory_directory_rejects_invalid_url():
    d = InMemoryDirectory()
    with pytest.raises(ValueError):
        d.add(PUBLIC_ID_A, "ftp://example.com", "alice@example.com")
    with pytest.raises(ValueError):
        d.add(PUBLIC_ID_A, "not-a-url", "alice@example.com")


def test_in_memory_directory_rejects_invalid_account_id():
    d = InMemoryDirectory()
    with pytest.raises(ValueError):
        d.add(PUBLIC_ID_A, "http://127.0.0.1:8001", "")
    with pytest.raises(ValueError):
        d.add(PUBLIC_ID_A, "http://127.0.0.1:8001", "../etc/passwd")


def test_in_memory_directory_all_entries():
    d = InMemoryDirectory()
    d.add(PUBLIC_ID_A, "http://127.0.0.1:8001", "alice@example.com")
    d.add(PUBLIC_ID_B, "http://127.0.0.1:8002", "bob@example.com")
    entries = d.all_entries()
    keys = {e[0] for e in entries}
    assert keys == {PUBLIC_ID_A, PUBLIC_ID_B}


def test_local_contact_list_persists(tmp_path):
    path = tmp_path / "contacts.json"
    d1 = LocalContactList(path)
    d1.add(PUBLIC_ID_A, "http://127.0.0.1:8001", "alice@example.com")
    d2 = LocalContactList(path)
    assert d2.lookup(PUBLIC_ID_A) == "http://127.0.0.1:8001"


def test_local_contact_list_overwrites(tmp_path):
    path = tmp_path / "contacts.json"
    d = LocalContactList(path)
    d.add(PUBLIC_ID_A, "http://127.0.0.1:8001", "alice@example.com")
    d.add(PUBLIC_ID_A, "http://127.0.0.1:9999", "alice@example.com")
    assert d.lookup(PUBLIC_ID_A) == "http://127.0.0.1:9999"


def test_local_contact_list_handles_corrupt_file(tmp_path):
    path = tmp_path / "contacts.json"
    path.write_text("not json at all", encoding="utf-8")
    # Should not raise; just start empty.
    d = LocalContactList(path)
    assert d.lookup(PUBLIC_ID_A) is None
    d.add(PUBLIC_ID_A, "http://127.0.0.1:8001", "alice@example.com")
    assert d.lookup(PUBLIC_ID_A) == "http://127.0.0.1:8001"


def test_local_contact_list_skips_invalid_entries(tmp_path):
    path = tmp_path / "contacts.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "contacts": [
                    {"public_id": PUBLIC_ID_A, "base_url": "http://127.0.0.1:8001", "account_id": "alice@example.com"},
                    {"public_id": "x", "base_url": "not a url", "account_id": "bad"},
                    {"public_id": "y", "base_url": "http://127.0.0.1:8002", "account_id": "../escape"},
                ],
            }
        ),
        encoding="utf-8",
    )
    d = LocalContactList(path)
    assert d.lookup(PUBLIC_ID_A) == "http://127.0.0.1:8001"
    assert d.lookup("x") is None
    assert d.lookup("y") is None
