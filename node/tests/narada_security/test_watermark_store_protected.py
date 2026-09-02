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


def test_watermark_store_rejects_tampered_data(tmp_path: Path):
    """A disk attacker who rewrites the watermark file is detected."""
    p = tmp_path / "wm.json"
    s = WatermarkStore(p, key=b"K" * 32)
    s.update("alice", 5)
    p.write_bytes(json.dumps({"alice": 999999}).encode())
    s2 = WatermarkStore(p, key=b"K" * 32)
    assert s2.get("alice") == -1


def test_watermark_store_rejects_missing_sidecar(tmp_path: Path):
    p = tmp_path / "wm.json"
    s = WatermarkStore(p, key=b"K" * 32)
    s.update("alice", 5)
    p.with_name(p.name + ".hmac").unlink()
    s2 = WatermarkStore(p, key=b"K" * 32)
    assert s2.get("alice") == -1


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
