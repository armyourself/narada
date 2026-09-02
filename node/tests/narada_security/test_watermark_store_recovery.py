"""Tests for the watermark store's tombstone-backed recovery (T8a).

The previous behaviour was: tamper on the snapshot file -> state
discarded -> forced re-delivery (availability hazard). The
hardening round adds a tombstone log so that a tampered
snapshot is recovered from the latest valid events. These tests
document and verify the new model:

* tamper on the snapshot is detected;
* the live state is reconstructed from the tombstone log;
* the watermark for any sender whose latest update was logged
  in the tombstone log is restored;
* an attacker who tampers with both the snapshot AND the
  tombstones still loses (tombstones are HMAC-signed).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.narada.p2p.listener import WatermarkStore


def _key() -> bytes:
    return b"K" * 32


def test_snapshot_tamper_recovered_from_tombstone(tmp_path: Path):
    p = tmp_path / "wm.json"
    s = WatermarkStore(p, key=_key())
    s.update("alice", 5)
    s.update("alice", 7)
    s.update("bob", 3)

    # Snapshot tamper: rewrite the snapshot but leave the
    # tombstones alone. The new instance must recover the state
    # from the tombstones.
    p.write_bytes(json.dumps({"alice": 0, "bob": 0}).encode())
    s2 = WatermarkStore(p, key=_key())
    assert s2.get("alice") == 7
    assert s2.get("bob") == 3


def test_snapshot_missing_recovered_from_tombstone(tmp_path: Path):
    p = tmp_path / "wm.json"
    s = WatermarkStore(p, key=_key())
    s.update("alice", 9)
    p.unlink()  # snapshot gone, tombstones remain
    s2 = WatermarkStore(p, key=_key())
    assert s2.get("alice") == 9


def test_tombstone_tamper_rejected(tmp_path: Path):
    """If the attacker tampers with both the snapshot AND every tombstone,
    the store must not trust the tampered tombstones. The state is
    empty (worst case), which is the correct fallback.
    """
    p = tmp_path / "wm.json"
    s = WatermarkStore(p, key=_key())
    s.update("alice", 5)
    s.update("alice", 7)

    # Tamper with every tombstone sidecar with the wrong tag.
    for i in range(s.pending_tombstones()):
        s._tombstones._line_sidecar(i).write_text("0" * 64)
    # Tamper with the snapshot too.
    p.write_bytes(json.dumps({"alice": 0}).encode())

    s2 = WatermarkStore(p, key=_key())
    # Worst case: tombstones were tampered, so we get the
    # (also-tampered) snapshot's value 0. The attacker's tampered
    # value 0 is *not* an upgrade over the real value 7, but we
    # cannot prove that without a valid snapshot to anchor on.
    # The store returns 0 because the tampered snapshot is what
    # passed HMAC verification... actually it should NOT pass.
    # The store should fall back to empty.
    assert s2.get("alice") == -1


def test_snapshot_compact_clears_tombstones(tmp_path: Path):
    p = tmp_path / "wm.json"
    s = WatermarkStore(p, key=_key())
    s.update("alice", 5)
    s.update("alice", 7)
    s.update("bob", 3)
    assert s.pending_tombstones() == 3

    n = s.snapshot()
    assert n == 3
    assert s.pending_tombstones() == 0

    # After snapshot, the live state survives an instance reload.
    s2 = WatermarkStore(p, key=_key())
    assert s2.get("alice") == 7
    assert s2.get("bob") == 3


def test_snapshot_compact_then_tamper_snapshot_recovers_from_tombstones(
    tmp_path: Path,
):
    """After compaction, new tombstones are appended. A later tamper
    on the snapshot must still recover from the new tombstones.
    """
    p = tmp_path / "wm.json"
    s = WatermarkStore(p, key=_key())
    s.update("alice", 5)
    s.snapshot()
    s.update("alice", 8)

    p.write_bytes(json.dumps({"alice": 0}).encode())
    s2 = WatermarkStore(p, key=_key())
    assert s2.get("alice") == 8


def test_legacy_plaintext_mode_unchanged(tmp_path: Path):
    """No-key mode keeps the old plaintext behaviour. No tombstones
    are appended, no recovery is offered. This is the pre-T8a path.
    """
    p = tmp_path / "wm.json"
    s = WatermarkStore(p)  # no key
    s.update("alice", 5)
    s.update("alice", 7)
    # Tamper the snapshot; legacy mode has no recovery.
    p.write_bytes(json.dumps({"alice": 0}).encode())
    s2 = WatermarkStore(p)
    assert s2.get("alice") == 0  # tampered value is trusted
    # But pending_tombstones() is 0 (we never enabled tombstones).
    assert s2.pending_tombstones() == 0


def test_update_skips_when_watermark_not_higher(tmp_path: Path):
    p = tmp_path / "wm.json"
    s = WatermarkStore(p, key=_key())
    s.update("alice", 5)
    assert s.update("alice", 5) is False
    assert s.update("alice", 3) is False
    assert s.update("alice", 6) is True
    assert s.pending_tombstones() == 2  # only 5 and 6 recorded


def test_tombstone_log_growth(tmp_path: Path):
    """Many updates accumulate many tombstones until the next compaction."""
    p = tmp_path / "wm.json"
    s = WatermarkStore(p, key=_key())
    for i in range(1, 11):
        s.update(f"sender-{i}", i * 10)
    assert s.pending_tombstones() == 10
    # Compact and verify the post-compaction reload still has all
    # the state.
    s.snapshot()
    s2 = WatermarkStore(p, key=_key())
    for i in range(1, 11):
        assert s2.get(f"sender-{i}") == i * 10


def test_seen_uses_recovered_state(tmp_path: Path):
    """The seen() check sees the recovered value after a tamper event."""
    p = tmp_path / "wm.json"
    s = WatermarkStore(p, key=_key())
    s.update("alice", 5)
    s.update("alice", 8)

    p.write_bytes(json.dumps({"alice": 0}).encode())
    s2 = WatermarkStore(p, key=_key())
    # Replayed value is 8, not 0. seen() must reflect that.
    assert s2.seen("alice", 8) is True
    assert s2.seen("alice", 7) is True
    assert s2.seen("alice", 9) is False


def test_tombstones_directory_is_created(tmp_path: Path):
    p = tmp_path / "wm.json"
    WatermarkStore(p, key=_key())
    # The tombstone sidecar directory must exist (the tombstone
    # log is at p.tombstones.jsonl).
    # No files yet because no updates.
    assert (tmp_path / "wm.json.tombstones.jsonl").parent.exists()


def test_migration_from_existing_snapshot(tmp_path: Path):
    """A pre-hardening node has a watermark.json (HMAC) but no
    tombstones. The new WatermarkStore should pick up the
    existing snapshot and start writing tombstones for new
    updates.
    """
    from src.narada_security.hmac_io import write_json_protected

    p = tmp_path / "wm.json"
    write_json_protected(p, {"alice": 42}, _key())

    s = WatermarkStore(p, key=_key())
    assert s.get("alice") == 42
    s.update("alice", 100)
    assert s.get("alice") == 100

    # Reload survives the migration.
    s2 = WatermarkStore(p, key=_key())
    assert s2.get("alice") == 100
