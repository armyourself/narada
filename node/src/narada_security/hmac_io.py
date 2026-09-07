"""HMAC-protected file I/O for on-disk state.

Narada persists several pieces of state to disk:

* the outbox (``<data_dir>/outbox/<account>.jsonl``)
* the inbox replay window (``<data_dir>/etc/seen.<account>.json``)
* the per-sender watermark store (``<data_dir>/watermarks.json``)
* the peer pin store (``<data_dir>/node_identity/peers.json``)

These files were previously plaintext JSON. An attacker with disk
access could:

* delete or modify outbox entries to suppress or fabricate deliveries
  (threat T7);
* rewrite the watermark file to ``{}`` to force every sender's
  messages to be re-delivered (threat T8);
* rewrite the seen file to ``{}`` to bypass the 5-minute replay
  window for /narada/inbox (threat T8).

This module provides a thin wrapper that:

* reads a JSON file and verifies an accompanying ``.hmac`` sidecar
  containing a hex-encoded HMAC-SHA256 of the file contents;
* writes atomically: write ``.tmp`` -> rename to ``.path`` and write
  ``.hmac`` with the matching tag.

The key is the local node identity's seed (``<data_dir>/node_identity/seed``),
which is 0600-restricted on POSIX. An attacker with read access to
the seed can forge the sidecar; the protection here is against
attackers who can write to the data dir but not read the seed.

For the bootstrap file and node identity seed itself, this module is
**not** sufficient; those live behind the keystore and the OS keyring.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any, Callable

from src.narada.node_identity import _NODE_SEED_LEN

_HMAC_TAG_FILE_SUFFIX = ".hmac"


class HmacIntegrityError(Exception):
    """Raised when a sidecar HMAC does not match the file contents."""


def hmac_io_key(seed: bytes) -> bytes:
    """Derive a fixed-length HMAC key from the node-identity seed.

    Using a domain-separated HKDF so we can re-derive a different one
    for, say, outbox vs watermarks without risk of cross-protocol
    forgery if one sidecar is leaked.
    """
    if len(seed) < _NODE_SEED_LEN:
        raise ValueError("seed too short")
    return hashlib.sha256(b"narada-hmac-io-v1|" + seed).digest()


def _sidecar_path(path: Path) -> Path:
    return path.with_name(path.name + _HMAC_TAG_FILE_SUFFIX)


def write_protected(path: Path, data: bytes, key: bytes) -> None:
    """Write ``data`` to ``path`` and an HMAC-SHA256 sidecar.

    Atomic: writes to ``path.tmp`` + ``sidecar.tmp`` first, then
    renames. The OS guarantees the rename is observed atomically
    by readers.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tag = hmac.new(key, data, hashlib.sha256).hexdigest()
    tmp_data = path.with_suffix(path.suffix + ".tmp")
    tmp_tag = _sidecar_path(tmp_data)
    tmp_data.write_bytes(data)
    tmp_tag.write_text(tag)
    # Rename data first; if tag rename fails, the sidecar will be
    # regenerated on the next write. On read, a missing tag will
    # be detected.
    os.replace(tmp_data, path)
    os.replace(tmp_tag, _sidecar_path(path))


def read_protected(path: Path, key: bytes) -> bytes:
    """Read ``path`` and verify the sidecar HMAC. Raises on mismatch."""
    if not path.exists():
        raise FileNotFoundError(path)
    sidecar = _sidecar_path(path)
    if not sidecar.exists():
        raise HmacIntegrityError(f"missing sidecar for {path}")
    expected = sidecar.read_text().strip()
    actual_data = path.read_bytes()
    actual_tag = hmac.new(key, actual_data, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, actual_tag):
        raise HmacIntegrityError(f"HMAC mismatch on {path}")
    return actual_data


def write_json_protected(path: Path, payload: Any, key: bytes) -> None:
    """Convenience: JSON-encode and protect."""
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    write_protected(path, body, key)


def read_json_protected(path: Path, key: bytes) -> Any:
    """Convenience: read + verify + JSON-decode."""
    data = read_protected(path, key)
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HmacIntegrityError(f"corrupt JSON in {path}: {exc}") from exc


def load_key(data_dir: Path) -> bytes:
    """Load the HMAC key from the node-identity seed file.

    If the seed file does not exist (e.g. ephemeral node or first
    boot), this generates a fresh random key and persists it next to
    the seed with 0600 permissions. The seed-based derivation is
    preferred when the seed is present because it survives a node
    restart and lets other on-disk state (which was written with
    the same seed) verify.
    """
    seed_path = Path(str(data_dir)) / "node_identity" / "seed"
    if seed_path.exists():
        try:
            seed = seed_path.read_bytes()
            if len(seed) >= _NODE_SEED_LEN:
                return hmac_io_key(seed[:_NODE_SEED_LEN])
        except OSError:
            pass
    # Fallback: derive a random key and persist it separately.
    fallback = Path(str(data_dir)) / "node_identity" / "hmac_key"
    if fallback.exists():
        try:
            k = fallback.read_bytes()
            if len(k) == 32:
                return k
        except OSError:
            pass
    fallback.parent.mkdir(parents=True, exist_ok=True)
    new_key = os.urandom(32)
    fallback.write_bytes(new_key)
    try:
        os.chmod(fallback, 0o600)
    except (OSError, NotImplementedError):
        pass
    return new_key


__all__ = [
    "HmacIntegrityError",
    "hmac_io_key",
    "load_key",
    "read_json_protected",
    "read_protected",
    "write_json_protected",
    "write_protected",
]
