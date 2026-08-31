"""Tests for the Lattice outbox."""

from __future__ import annotations

import json

import pytest

from src.lattice.outbox import Outbox, OutboxEntry


def _envelope_dict(message_id: str, recipient: str = "lattice1xyz") -> dict:
    return {
        "v": 1,
        "sender_public_id": "lattice1sender",
        "recipient_public_id": recipient,
        "message_id": message_id,
        "timestamp": 1700000000,
        "nonce": "AAAAAAAAAAAAAAAAAAAAAA==",
        "signature": "A" * 88,
        "body_ciphertext": "AAAA",
    }


def test_enqueue_creates_file(tmp_path):
    outbox = Outbox(tmp_path)
    outbox.enqueue(
        account_id="alice@example.com",
        recipient_public_id="lattice1xyz",
        envelope=_envelope_dict("m1"),
    )
    # The file is named after the account_id; the on-disk name keeps
    # only filesystem-safe characters.
    files = list((tmp_path / "outbox").glob("*.jsonl"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8").strip()
    record = json.loads(files[0].read_text(encoding="utf-8").strip().splitlines()[0])
    assert record["message_id"] == "m1"


def test_list_due_returns_only_due_entries(tmp_path):
    now = [1700000000]
    outbox = Outbox(tmp_path, now_fn=lambda: now[0])
    outbox.enqueue(
        account_id="alice@example.com",
        recipient_public_id="lattice1xyz",
        envelope=_envelope_dict("m1"),
        first_attempt_delay_seconds=0,
    )
    outbox.enqueue(
        account_id="alice@example.com",
        recipient_public_id="lattice1xyz",
        envelope=_envelope_dict("m2"),
        first_attempt_delay_seconds=300,
    )
    now[0] = 1700000100
    due = outbox.list_due("alice@example.com")
    assert {e.message_id for e in due} == {"m1"}


def test_mark_delivered_removes_entry(tmp_path):
    outbox = Outbox(tmp_path)
    outbox.enqueue(
        account_id="alice@example.com",
        recipient_public_id="lattice1xyz",
        envelope=_envelope_dict("m1"),
    )
    assert outbox.mark_delivered("alice@example.com", "m1") is True
    assert outbox.mark_delivered("alice@example.com", "m1") is False
    assert outbox.list_all("alice@example.com") == []


def test_mark_failed_increments_and_reschedules(tmp_path):
    now = [1700000000]
    outbox = Outbox(tmp_path, now_fn=lambda: now[0])
    outbox.enqueue(
        account_id="alice@example.com",
        recipient_public_id="lattice1xyz",
        envelope=_envelope_dict("m1"),
    )
    outbox.mark_failed("alice@example.com", "m1", "connection refused")
    after = outbox.list_all("alice@example.com")[0]
    assert after.attempt_count == 1
    assert after.last_error == "connection refused"
    # First backoff is 60s.
    assert after.next_attempt_at == 1700000000 + 60


def test_mark_failed_moves_to_dead_letter_after_max_attempts(tmp_path):
    outbox = Outbox(tmp_path)
    outbox.enqueue(
        account_id="alice@example.com",
        recipient_public_id="lattice1xyz",
        envelope=_envelope_dict("m1"),
    )
    # 5 attempts = max; the 5th failure moves to dead letter.
    for i in range(5):
        updated = outbox.mark_failed("alice@example.com", "m1", f"err {i}")
        assert updated is not None
    # Active queue is empty; the dead-letter file has one line.
    assert outbox.list_all("alice@example.com") == []
    dead_files = list((tmp_path / "outbox" / "dead-letter").glob("*.jsonl"))
    assert len(dead_files) == 1
    record = json.loads(dead_files[0].read_text(encoding="utf-8").strip().splitlines()[0])
    assert record["message_id"] == "m1"
    assert record["attempt_count"] == 5


def test_outbox_persists_across_reload(tmp_path):
    outbox1 = Outbox(tmp_path)
    outbox1.enqueue(
        account_id="alice@example.com",
        recipient_public_id="lattice1xyz",
        envelope=_envelope_dict("m1"),
    )
    outbox1.enqueue(
        account_id="alice@example.com",
        recipient_public_id="lattice1xyz",
        envelope=_envelope_dict("m2"),
    )
    outbox2 = Outbox(tmp_path)
    assert {e.message_id for e in outbox2.list_all("alice@example.com")} == {"m1", "m2"}


def test_remove_unconditionally(tmp_path):
    outbox = Outbox(tmp_path)
    outbox.enqueue(
        account_id="alice@example.com",
        recipient_public_id="lattice1xyz",
        envelope=_envelope_dict("m1"),
    )
    assert outbox.remove("alice@example.com", "m1") is True
    assert outbox.list_all("alice@example.com") == []


def test_account_id_with_at_sign(tmp_path):
    outbox = Outbox(tmp_path)
    outbox.enqueue(
        account_id="alice@example.com",
        recipient_public_id="lattice1xyz",
        envelope=_envelope_dict("m1"),
    )
    # The on-disk file is named after the (sanitised) account_id.
    files = list((tmp_path / "outbox").glob("*.jsonl"))
    assert len(files) == 1


def test_list_all_accounts(tmp_path):
    outbox = Outbox(tmp_path)
    assert outbox.list_all_accounts() == []
    outbox.enqueue(
        account_id="alice@example.com",
        recipient_public_id="lattice1xyz",
        envelope=_envelope_dict("m1"),
    )
    outbox.enqueue(
        account_id="bob@example.com",
        recipient_public_id="lattice1xyz",
        envelope=_envelope_dict("m2"),
    )
    accounts = set(outbox.list_all_accounts())
    assert "alice@example.com" in accounts
    assert "bob@example.com" in accounts
