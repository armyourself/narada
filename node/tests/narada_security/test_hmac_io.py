"""Tests for HMAC-protected file I/O (threats T7+T8)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.narada_security.hmac_io import (
    HmacIntegrityError,
    hmac_io_key,
    load_key,
    read_json_protected,
    read_protected,
    write_json_protected,
    write_protected,
)


def _key() -> bytes:
    return os.urandom(32)


def test_roundtrip_bytes(tmp_path: Path):
    p = tmp_path / "data.bin"
    k = _key()
    body = b"hello world"
    write_protected(p, body, k)
    assert p.exists()
    assert p.with_name(p.name + ".hmac").exists()
    assert read_protected(p, k) == body


def test_roundtrip_json(tmp_path: Path):
    p = tmp_path / "data.json"
    k = _key()
    payload = {"a": 1, "b": ["x", "y"]}
    write_json_protected(p, payload, k)
    assert read_json_protected(p, k) == payload


def test_tampered_file_detected(tmp_path: Path):
    p = tmp_path / "data.bin"
    k = _key()
    write_protected(p, b"hello", k)
    # Tamper with the data after write.
    p.write_bytes(b"goodbye")
    with pytest.raises(HmacIntegrityError):
        read_protected(p, k)


def test_tampered_sidecar_detected(tmp_path: Path):
    p = tmp_path / "data.bin"
    k = _key()
    write_protected(p, b"hello", k)
    sidecar = p.with_name(p.name + ".hmac")
    sidecar.write_text("0" * 64)
    with pytest.raises(HmacIntegrityError):
        read_protected(p, k)


def test_missing_sidecar_detected(tmp_path: Path):
    p = tmp_path / "data.bin"
    k = _key()
    write_protected(p, b"hello", k)
    p.with_name(p.name + ".hmac").unlink()
    with pytest.raises(HmacIntegrityError):
        read_protected(p, k)


def test_missing_file_raises_filenotfound(tmp_path: Path):
    p = tmp_path / "missing.bin"
    k = _key()
    with pytest.raises(FileNotFoundError):
        read_protected(p, k)


def test_wrong_key_rejected(tmp_path: Path):
    p = tmp_path / "data.bin"
    write_protected(p, b"hello", _key())
    with pytest.raises(HmacIntegrityError):
        read_protected(p, _key())


def test_load_key_returns_32_bytes(tmp_path: Path):
    k = load_key(tmp_path)
    assert len(k) == 32
    # Subsequent calls return the same key (persistence).
    assert load_key(tmp_path) == k


def test_load_key_uses_seed_when_present(tmp_path: Path):
    seed = b"\x42" * 32
    seed_path = tmp_path / "node_identity" / "seed"
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    seed_path.write_bytes(seed)
    k = load_key(tmp_path)
    # Same seed -> same derived key.
    assert k == hmac_io_key(seed)


def test_load_key_returns_random_when_no_seed(tmp_path: Path):
    k1 = load_key(tmp_path / "fresh")
    k2 = load_key(tmp_path / "fresh2")
    # Distinct data dirs -> distinct random keys.
    assert k1 != k2
    # Each is 32 bytes.
    assert len(k1) == 32
    assert len(k2) == 32


def test_corrupt_json_raises_integrity_error(tmp_path: Path):
    p = tmp_path / "data.json"
    k = _key()
    # Write raw bytes that are valid JSON-LD after hex... actually
    # let's just write invalid JSON and a valid tag.
    from src.narada_security.hmac_io import write_protected

    write_protected(p, b"not json", k)
    with pytest.raises(HmacIntegrityError):
        read_json_protected(p, k)


def test_atomic_write_does_not_leak_tmp(tmp_path: Path):
    p = tmp_path / "data.bin"
    k = _key()
    write_protected(p, b"hello", k)
    # No .tmp files left behind.
    assert not list(tmp_path.glob("*.tmp"))
    # The .hmac sidecar exists.
    assert p.with_name(p.name + ".hmac").exists()
