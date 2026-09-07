"""Unit tests for :mod:`gateway.gateway.mapping`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gateway.gateway.errors import NoMappingError
from gateway.gateway.mapping import IdentityMapping


def test_lookup_narada_to_smtp_hits(alice_narada_id):
    m = IdentityMapping(narada_to_smtp={alice_narada_id: "alice@example.com"})
    assert m.lookup_narada_to_smtp(alice_narada_id) == "alice@example.com"


def test_lookup_narada_to_smtp_missing_raises(alice_narada_id):
    m = IdentityMapping()
    with pytest.raises(NoMappingError):
        m.lookup_narada_to_smtp(alice_narada_id)


def test_lookup_smtp_to_narada_case_insensitive(alice_narada_id):
    m = IdentityMapping(smtp_to_narada={"alice@example.com": alice_narada_id})
    assert m.lookup_smtp_to_narada("Alice@Example.com") == alice_narada_id


def test_try_lookup_returns_none(alice_narada_id):
    m = IdentityMapping()
    assert m.try_lookup_narada_to_smtp(alice_narada_id) is None
    assert m.try_lookup_smtp_to_narada("alice@example.com") is None


def test_round_trip_via_file(tmp_path: Path, alice_narada_id):
    path = tmp_path / "m.json"
    m = IdentityMapping(
        narada_to_smtp={alice_narada_id: "alice@example.com"},
        smtp_to_narada={"alice@example.com": alice_narada_id},
    )
    m.save(path)
    fresh = IdentityMapping.from_file(path)
    assert fresh.lookup_narada_to_smtp(alice_narada_id) == "alice@example.com"
    assert fresh.lookup_smtp_to_narada("alice@example.com") == alice_narada_id


def test_reload_from_file(tmp_path: Path, alice_narada_id, bob_narada_id):
    path = tmp_path / "m.json"
    path.write_bytes(b'{"narada_to_smtp": {}, "smtp_to_narada": {}}')
    m = IdentityMapping.from_file(path)
    assert list(m.narada_ids()) == []
    path.write_bytes(
        json.dumps(
            {
                "narada_to_smtp": {alice_narada_id: "alice@example.com"},
                "smtp_to_narada": {"bob@example.com": bob_narada_id},
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    m.reload_from_file(path)
    assert m.lookup_narada_to_smtp(alice_narada_id) == "alice@example.com"
    assert m.lookup_smtp_to_narada("bob@example.com") == bob_narada_id


def test_invalid_id_rejected():
    with pytest.raises(ValueError):
        IdentityMapping(narada_to_smtp={"not-a-narada-id": "alice@example.com"})


def test_invalid_email_rejected(alice_narada_id):
    with pytest.raises(ValueError):
        IdentityMapping(smtp_to_narada={"not-an-email": alice_narada_id})
