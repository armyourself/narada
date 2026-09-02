"""Tests for the Phase 3 commit 5-7 infrastructure:

* HandlerRegistry
* PeerBook + PeerState liveness
* WatermarkStore (commit 6: network-level dedup)
* build_sync_handler (commit 5: sync endpoint)
* enqueue_for_peer / drain_peer_pushes (commit 5: push channel)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.narada.p2p.listener import (
    HandlerRegistry,
    PeerBook,
    PeerState,
    WatermarkStore,
    build_sync_handler,
    drain_peer_pushes,
    enqueue_for_peer,
)


# --- HandlerRegistry -----------------------------------------------------


def test_handler_registry_dispatches_by_type():
    reg = HandlerRegistry()

    @reg.register("echo")
    def _echo(payload, peer):
        return {"type": "echo.result", "value": payload.get("value")}

    out = reg.dispatch({"type": "echo", "value": 42}, ("127.0.0.1", 1234))
    assert out == {"type": "echo.result", "value": 42}


def test_handler_registry_unknown_type_returns_error():
    reg = HandlerRegistry()
    out = reg.dispatch({"type": "missing"}, ("127.0.0.1", 1234))
    assert out["type"] == "error"
    assert "missing" in out["message"]


def test_handler_registry_missing_type_returns_error():
    reg = HandlerRegistry()
    out = reg.dispatch({}, ("127.0.0.1", 1234))
    assert out["type"] == "error"


def test_handler_registry_handler_exception_caught():
    reg = HandlerRegistry()

    @reg.register("boom")
    def _boom(payload, peer):
        raise RuntimeError("nope")

    out = reg.dispatch({"type": "boom"}, ("127.0.0.1", 1234))
    assert out["type"] == "error"
    assert "nope" in out["message"]


# --- PeerBook liveness ---------------------------------------------------


def test_peer_book_upsert_creates_state():
    pb = PeerBook()
    st = pb.upsert("10.0.0.1:4440")
    assert st.endpoint == "10.0.0.1:4440"
    assert pb.get("10.0.0.1:4440") is st


def test_peer_book_touch_resets_down_and_missed():
    pb = PeerBook()
    st = pb.upsert("10.0.0.1:4440")
    st.down = True
    st.missed_pings = 5
    pb.touch("10.0.0.1:4440")
    assert st.down is False
    assert st.missed_pings == 0
    assert st.last_ping_ok is True


def test_peer_book_mark_missed_marks_down_after_threshold():
    pb = PeerBook()
    pb.upsert("10.0.0.1:4440")
    pb.mark_missed("10.0.0.1:4440")
    pb.mark_missed("10.0.0.1:4440")
    assert pb.get("10.0.0.1:4440").down is False
    pb.mark_missed("10.0.0.1:4440")
    assert pb.get("10.0.0.1:4440").down is True


def test_peer_book_live_endpoints_excludes_down():
    pb = PeerBook()
    pb.upsert("a:1")
    pb.upsert("b:2")
    pb.get("b:2").down = True
    assert pb.live_endpoints() == ["a:1"]


# --- WatermarkStore ------------------------------------------------------


def test_watermark_store_starts_at_minus_one(tmp_path: Path):
    s = WatermarkStore(tmp_path / "wm.json")
    assert s.get("alice") == -1
    assert s.seen("alice", 0) is False  # 0 > -1, so NOT seen


def test_watermark_store_update_persists(tmp_path: Path):
    p = tmp_path / "wm.json"
    s = WatermarkStore(p)
    assert s.update("alice", 10) is True
    assert s.update("alice", 5) is False  # older; no change
    assert s.update("alice", 11) is True
    # Reload from disk.
    s2 = WatermarkStore(p)
    assert s2.get("alice") == 11
    assert s2.all() == {"alice": 11}


def test_watermark_store_seen_returns_true_after_update(tmp_path: Path):
    s = WatermarkStore(tmp_path / "wm.json")
    s.update("alice", 10)
    assert s.seen("alice", 10) is True
    assert s.seen("alice", 9) is True
    assert s.seen("alice", 11) is False


def test_watermark_store_missing_file_returns_minus_one(tmp_path: Path):
    s = WatermarkStore(tmp_path / "does-not-exist.json")
    assert s.get("alice") == -1


def test_watermark_store_corrupt_file_returns_minus_one(tmp_path: Path):
    p = tmp_path / "wm.json"
    p.write_text("not json")
    s = WatermarkStore(p)
    assert s.get("alice") == -1


# --- build_sync_handler --------------------------------------------------


def _write_mailbox(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, separators=(",", ":")) + "\n")


def test_sync_handler_returns_entries_since_received_at(tmp_path: Path):
    mailbox = tmp_path / "alice.jsonl"
    _write_mailbox(
        mailbox,
        [
            {"received_at": 100, "subject": "old", "sender_public_id": "bob"},
            {"received_at": 200, "subject": "new", "sender_public_id": "bob"},
            {"received_at": 300, "subject": "newer", "sender_public_id": "carol"},
        ],
    )
    wm = WatermarkStore(tmp_path / "wm.json")
    handler = build_sync_handler(
        account_id_getter=lambda: {"alice@example.com": str(mailbox)},
        watermark_store=wm,
    )
    out = handler(
        {"type": "sync.fetch", "account_id": "alice@example.com", "since": 150},
        ("x", 0),
    )
    assert out["type"] == "sync.fetch.result"
    rtimes = sorted(e["received_at"] for e in out["entries"])
    assert rtimes == [200, 300]


def test_sync_handler_unknown_account_returns_error(tmp_path: Path):
    handler = build_sync_handler(
        account_id_getter=lambda: {},
        watermark_store=WatermarkStore(tmp_path / "wm.json"),
    )
    out = handler({"type": "sync.fetch", "account_id": "x"}, ("x", 0))
    assert out["type"] == "error"
    assert "unknown account_id" in out["message"]


def test_sync_handler_updates_watermark_to_received_at(tmp_path: Path):
    mailbox = tmp_path / "a.jsonl"
    _write_mailbox(
        mailbox,
        [
            {"received_at": 10, "sender_public_id": "bob"},
            {"received_at": 50, "sender_public_id": "bob"},
        ],
    )
    wm = WatermarkStore(tmp_path / "wm.json")
    handler = build_sync_handler(
        account_id_getter=lambda: {"a": str(mailbox)},
        watermark_store=wm,
    )
    handler({"type": "sync.fetch", "account_id": "a", "since": 0}, ("x", 0))
    assert wm.get("bob") == 50
    assert wm.seen("bob", 50) is True


# --- enqueue_for_peer + drain_peer_pushes --------------------------------


def test_enqueue_and_drain_peer_pushes():
    pb = PeerBook()
    assert enqueue_for_peer(pb, "a:1", {"type": "x"}) is True
    assert enqueue_for_peer(pb, "a:1", {"type": "y"}) is True
    peer = pb.get("a:1")
    drained = drain_peer_pushes(peer)
    assert [d["type"] for d in drained] == ["x", "y"]
    # Queue empty after drain.
    assert drain_peer_pushes(peer) == []


def test_enqueue_drops_on_full_queue():
    pb = PeerBook()
    peer = pb.upsert("a:1")
    # Force the queue to be full by stuffing it directly.
    from queue import Queue

    peer.push_queue = Queue(maxsize=2)
    assert enqueue_for_peer(pb, "a:1", {"i": 1}) is True
    assert enqueue_for_peer(pb, "a:1", {"i": 2}) is True
    # Next push must drop, not block.
    assert enqueue_for_peer(pb, "a:1", {"i": 3}) is False
