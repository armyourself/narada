"""Tests for KeyRotationStore (Phase 1 key rotation, on-the-wire)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.narada.key_rotation_store import KeyRotationRecord, KeyRotationStore


def _key() -> bytes:
    return b"K" * 32


def _now() -> int:
    return int(time.time())


def test_record_then_lookup_active(tmp_path: Path):
    p = tmp_path / "rot.json"
    s = KeyRotationStore(p, key=_key())
    rec = s.record(
        prior_public_id="narada1aaa",
        new_public_id="narada1bbb",
        not_after=_now() + 10_000,
    )
    assert rec.prior_public_id == "narada1aaa"
    assert rec.new_public_id == "narada1bbb"
    assert s.lookup("narada1aaa") == rec


def test_lookup_returns_none_after_not_after(tmp_path: Path):
    p = tmp_path / "rot.json"
    s = KeyRotationStore(p, key=_key())
    s.record(
        prior_public_id="narada1aaa",
        new_public_id="narada1bbb",
        not_after=1_000,
    )
    # now=2000 > not_after=1000: rotation is closed
    assert s.lookup("narada1aaa", now=2_000) is None


def test_lookup_active_within_window(tmp_path: Path):
    p = tmp_path / "rot.json"
    s = KeyRotationStore(p, key=_key())
    s.record(
        prior_public_id="narada1aaa",
        new_public_id="narada1bbb",
        not_after=10_000,
    )
    # exactly at the boundary: still active
    assert s.lookup("narada1aaa", now=10_000) is not None
    # one second past: closed
    assert s.lookup("narada1aaa", now=10_001) is None


def test_lookup_unknown_returns_none(tmp_path: Path):
    p = tmp_path / "rot.json"
    s = KeyRotationStore(p, key=_key())
    assert s.lookup("narada1zzz") is None


def test_record_overwrites_previous(tmp_path: Path):
    p = tmp_path / "rot.json"
    s = KeyRotationStore(p, key=_key())
    s.record("narada1aaa", "narada1bbb", not_after=_now() + 1000)
    s.record("narada1aaa", "narada1ccc", not_after=_now() + 2000)
    rec = s.lookup("narada1aaa")
    assert rec is not None
    assert rec.new_public_id == "narada1ccc"


def test_remove_returns_true_when_present(tmp_path: Path):
    p = tmp_path / "rot.json"
    s = KeyRotationStore(p, key=_key())
    s.record("narada1aaa", "narada1bbb", not_after=_now() + 1_000_000)
    assert s.remove("narada1aaa") is True
    assert s.lookup("narada1aaa") is None


def test_remove_returns_false_when_absent(tmp_path: Path):
    p = tmp_path / "rot.json"
    s = KeyRotationStore(p, key=_key())
    assert s.remove("narada1aaa") is False


def test_persists_across_instances(tmp_path: Path):
    p = tmp_path / "rot.json"
    a = KeyRotationStore(p, key=_key())
    a.record("narada1aaa", "narada1bbb", not_after=_now() + 100_000)
    b = KeyRotationStore(p, key=_key())
    rec = b.lookup("narada1aaa")
    assert rec is not None
    assert rec.new_public_id == "narada1bbb"


def test_tampered_file_rejected(tmp_path: Path):
    p = tmp_path / "rot.json"
    s = KeyRotationStore(p, key=_key())
    s.record("narada1aaa", "narada1bbb", not_after=_now() + 100_000)
    p.write_bytes(
        json.dumps(
            {
                "narada1xxx": {
                    "prior_public_id": "narada1xxx",
                    "new_public_id": "evil",
                    "not_after": 99_999_999,
                    "received_at": 0,
                }
            }
        ).encode()
    )
    s2 = KeyRotationStore(p, key=_key())
    assert s2.lookup("narada1aaa") is None
    assert s2.lookup("narada1xxx") is None


def test_missing_sidecar_rejected(tmp_path: Path):
    p = tmp_path / "rot.json"
    s = KeyRotationStore(p, key=_key())
    s.record("narada1aaa", "narada1bbb", not_after=_now() + 100_000)
    p.with_name(p.name + ".hmac").unlink()
    s2 = KeyRotationStore(p, key=_key())
    assert s2.lookup("narada1aaa") is None


def test_wrong_key_rejected(tmp_path: Path):
    p = tmp_path / "rot.json"
    s = KeyRotationStore(p, key=_key())
    s.record("narada1aaa", "narada1bbb", not_after=_now() + 100_000)
    s2 = KeyRotationStore(p, key=b"L" * 32)
    assert s2.lookup("narada1aaa") is None


def test_plaintext_fallback(tmp_path: Path):
    p = tmp_path / "rot.json"
    s = KeyRotationStore(p)  # no key
    s.record("narada1aaa", "narada1bbb", not_after=_now() + 100_000)
    assert p.exists()
    assert not p.with_name(p.name + ".hmac").exists()
    s2 = KeyRotationStore(p)
    assert s2.lookup("narada1aaa") is not None


def test_record_to_from_dict_roundtrip():
    rec = KeyRotationRecord(
        prior_public_id="narada1aaa",
        new_public_id="narada1bbb",
        not_after=12345,
        received_at=67890,
    )
    rt = KeyRotationRecord.from_dict(rec.to_dict())
    assert rt == rec


def test_record_is_active_uses_now_when_omitted():
    rec = KeyRotationRecord(
        prior_public_id="a",
        new_public_id="b",
        not_after=int(time.time()) + 1000,
        received_at=0,
    )
    assert rec.is_active() is True
    expired = KeyRotationRecord(
        prior_public_id="a",
        new_public_id="b",
        not_after=0,
        received_at=0,
    )
    assert expired.is_active() is False


def test_all_returns_every_record(tmp_path: Path):
    p = tmp_path / "rot.json"
    s = KeyRotationStore(p, key=_key())
    s.record("a", "b", not_after=_now() + 1)
    s.record("c", "d", not_after=_now() + 2)
    all_recs = s.all()
    assert set(all_recs.keys()) == {"a", "c"}
