"""Tests for the HMAC-protected WatermarkStore (threat T8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.narada.p2p.listener import WatermarkStore


def test_watermark_store_persists_with_hmac(tmp_path: Path):
    p = tmp_path / "wm.json"
    s = WatermarkStore(p, key=b"K" * 32)
    s.update("alice", 10)
    assert p.exists()
    sidecar = p.with_name(p.name + ".hmac")
    assert sidecar.exists()
    assert len(sidecar.read_text().strip()) == 64


def test_watermark_store_reload_verifies_hmac(tmp_path: Path):
    p = tmp_path / "wm.json"
    s = WatermarkStore(p, key=b"K" * 32)
    s.update("alice", 5)
    s.update("bob", 9)
    s2 = WatermarkStore(p, key=b"K" * 32)
    assert s2.get("alice") == 5
    assert s2.get("bob") == 9


def test_watermark_store_snapshot_tamper_recovered_from_tombstones(tmp_path: Path):
    """A disk attacker who rewrites the snapshot file cannot forge a
    valid HMAC; the store falls back to the tombstone log to
    recover the live state. The tampered value is NOT trusted
    because it didn't come from a valid snapshot or a valid
    tombstone."""
    p = tmp_path / "wm.json"
    s = WatermarkStore(p, key=b"K" * 32)
    s.update("alice", 5)
    # Replace the snapshot with a fake, attacker-controlled value.
    p.write_bytes(json.dumps({"alice": 999999}).encode())
    s2 = WatermarkStore(p, key=b"K" * 32)
    # Recovery path: replay tombstones, which say alice = 5.
    assert s2.get("alice") == 5


def test_watermark_store_missing_sidecar_recovered_from_tombstones(tmp_path: Path):
    """A missing sidecar triggers the same fallback as a tampered one."""
    p = tmp_path / "wm.json"
    s = WatermarkStore(p, key=b"K" * 32)
    s.update("alice", 5)
    p.with_name(p.name + ".hmac").unlink()
    s2 = WatermarkStore(p, key=b"K" * 32)
    assert s2.get("alice") == 5


def test_watermark_store_wrong_key_rejected(tmp_path: Path):
    p = tmp_path / "wm.json"
    s = WatermarkStore(p, key=b"K" * 32)
    s.update("alice", 5)
    s2 = WatermarkStore(p, key=b"L" * 32)
    assert s2.get("alice") == -1


def test_watermark_store_no_key_uses_plaintext(tmp_path: Path):
    """Backward compat: a key-less WatermarkStore reads/writes plaintext."""
    p = tmp_path / "wm.json"
    s = WatermarkStore(p)
    s.update("alice", 7)
    assert p.exists()
    assert not p.with_name(p.name + ".hmac").exists()
    s2 = WatermarkStore(p)
    assert s2.get("alice") == 7
