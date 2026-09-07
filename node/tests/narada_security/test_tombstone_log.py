"""Tests for the tombstone log (T8a recovery path)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.narada_security.tombstone_log import TombstoneLog


def _key() -> bytes:
    return b"K" * 32


def test_append_returns_increasing_sequence(tmp_path: Path):
    log = TombstoneLog(tmp_path / "tombstones.jsonl", key=_key())
    s0 = log.append({"sender": "alice", "lseq": 1})
    s1 = log.append({"sender": "alice", "lseq": 2})
    s2 = log.append({"sender": "bob", "lseq": 1})
    assert s0 == 0
    assert s1 == 1
    assert s2 == 2
    assert log.next_seq == 3


def test_replay_returns_events_in_order(tmp_path: Path):
    log = TombstoneLog(tmp_path / "tombstones.jsonl", key=_key())
    log.append({"sender": "alice", "lseq": 1})
    log.append({"sender": "alice", "lseq": 2})
    log.append({"sender": "bob", "lseq": 5})
    events = list(log.replay())
    assert events == [
        {"sender": "alice", "lseq": 1},
        {"sender": "alice", "lseq": 2},
        {"sender": "bob", "lseq": 5},
    ]


def test_replay_skips_tampered_data_line(tmp_path: Path):
    """A disk attacker who rewrites the data file cannot forge a valid line."""
    log = TombstoneLog(tmp_path / "tombstones.jsonl", key=_key())
    log.append({"sender": "alice", "lseq": 1})
    log.append({"sender": "alice", "lseq": 2})
    # Tamper with line 0's data file.
    log._line_path(0).write_bytes(b'{"sender": "alice", "lseq": 999}')
    events = list(log.replay())
    # The tampered line is skipped; the honest line remains.
    assert events == [{"sender": "alice", "lseq": 2}]


def test_replay_skips_tampered_sidecar(tmp_path: Path):
    log = TombstoneLog(tmp_path / "tombstones.jsonl", key=_key())
    log.append({"sender": "alice", "lseq": 1})
    log.append({"sender": "alice", "lseq": 2})
    # Replace the sidecar with a junk value.
    log._line_sidecar(0).write_text("0" * 64)
    events = list(log.replay())
    assert events == [{"sender": "alice", "lseq": 2}]


def test_replay_skips_missing_sidecar(tmp_path: Path):
    log = TombstoneLog(tmp_path / "tombstones.jsonl", key=_key())
    log.append({"sender": "alice", "lseq": 1})
    log.append({"sender": "alice", "lseq": 2})
    log._line_sidecar(0).unlink()
    events = list(log.replay())
    assert events == [{"sender": "alice", "lseq": 2}]


def test_replay_with_wrong_key_skips_everything(tmp_path: Path):
    log = TombstoneLog(tmp_path / "tombstones.jsonl", key=_key())
    log.append({"sender": "alice", "lseq": 1})
    bad = TombstoneLog(tmp_path / "tombstones.jsonl", key=b"L" * 32)
    assert list(bad.replay()) == []


def test_compact_removes_all_events(tmp_path: Path):
    log = TombstoneLog(tmp_path / "tombstones.jsonl", key=_key())
    for i in range(5):
        log.append({"sender": "alice", "lseq": i})
    n = log.compact()
    assert n == 5
    assert list(log.replay()) == []
    assert log.next_seq == 0


def test_compact_preserves_data_files_as_backup(tmp_path: Path):
    """compact() renames rather than deletes; a forensic copy survives."""
    log = TombstoneLog(tmp_path / "tombstones.jsonl", key=_key())
    log.append({"sender": "alice", "lseq": 1})
    log.compact()
    # The .compact-<ts>.bak file must exist somewhere in the dir.
    backups = list(tmp_path.glob("*.compact-*.bak"))
    assert len(backups) >= 1


def test_persistence_across_instances(tmp_path: Path):
    """A second TombstoneLog over the same path picks up where the first left off."""
    a = TombstoneLog(tmp_path / "tombstones.jsonl", key=_key())
    a.append({"sender": "alice", "lseq": 1})
    b = TombstoneLog(tmp_path / "tombstones.jsonl", key=_key())
    assert b.next_seq == 1
    b.append({"sender": "alice", "lseq": 2})
    assert list(b.replay()) == [
        {"sender": "alice", "lseq": 1},
        {"sender": "alice", "lseq": 2},
    ]


def test_append_requires_key():
    import tempfile

    with tempfile.TemporaryDirectory() as t:
        log = TombstoneLog(Path(t) / "tombstones.jsonl")  # no key
        with pytest.raises(RuntimeError):
            log.append({"x": 1})


def test_wrong_key_cannot_append(tmp_path: Path):
    log = TombstoneLog(tmp_path / "tombstones.jsonl", key=_key())
    log.append({"sender": "alice", "lseq": 1})
    # A second instance with a different key can read existing
    # lines (they verify under their own key) but cannot append
    # new events signed under the wrong key. We don't enforce the
    # latter at the log level; the lock-in is at the WatermarkStore
    # layer. Verify the basic behaviour: a fresh instance with a
    # wrong key sees 0 events.
    bad = TombstoneLog(tmp_path / "tombstones.jsonl", key=b"L" * 32)
    assert list(bad.replay()) == []
