"""Unit tests for :mod:`src.narada.relay.handlers` (in-process)."""

from __future__ import annotations

import secrets
import time
from pathlib import Path

import pytest

from src.narada.node_identity import NaradaNodeIdentity
from src.narada.relay.handlers import (
    build_deposit_handler,
    build_drop_handler,
    build_fetch_handler,
)
from src.narada.relay.receipt import verify_stored_receipt
from src.narada.relay.store import RelayStore


@pytest.fixture
def handlers(tmp_path: Path):
    relay = NaradaNodeIdentity.generate()
    store = RelayStore(tmp_path, master_key=secrets.token_bytes(32))
    return (
        build_deposit_handler(store=store, relay_identity=relay),
        build_fetch_handler(store=store),
        build_drop_handler(store=store),
        store,
        relay,
    )


def _envelope(recipient: str = "narada1qtest") -> dict:
    return {
        "v": 1,
        "sender_public_id": "narada1alice...",
        "recipient_public_id": recipient,
        "message_id": secrets.token_hex(8),
        "timestamp": int(time.time()),
        "nonce": secrets.token_hex(16),
        "signature": secrets.token_hex(64),
        "body_ciphertext": secrets.token_hex(64),
    }


def test_deposit_returns_signed_receipt(handlers):
    deposit, _, _, _, relay = handlers
    env = _envelope()
    reply = deposit(
        {"type": "relay.deposit", "v": 1, "envelope": env},
        ("peer", 0),
    )
    assert reply["type"] == "relay.stored"
    assert reply["recipient_public_id"] == env["recipient_public_id"]
    # The relay signed it.
    from src.narada.relay.receipt import StoredReceipt
    receipt = StoredReceipt.from_dict(reply)
    assert receipt.relay_node_id == relay.public_id
    assert verify_stored_receipt(receipt, expected_message_id=env["message_id"])


def test_deposit_rejects_bad_version(handlers):
    deposit, _, _, _, _ = handlers
    reply = deposit(
        {"type": "relay.deposit", "v": 99, "envelope": _envelope()},
        ("peer", 0),
    )
    assert reply["type"] == "error"


def test_fetch_returns_only_owners(handlers):
    deposit, fetch, _, _, _ = handlers
    env = _envelope("narada1qtest")
    deposit({"type": "relay.deposit", "v": 1, "envelope": env}, ("peer", 0))
    reply = fetch(
        {
            "type": "relay.fetch",
            "v": 1,
            "recipient_public_id": "narada1qtest",
            "limit": 64,
        },
        ("peer", 0),
    )
    assert reply["type"] == "relay.fetch.result"
    assert len(reply["deposits"]) == 1
    assert reply["deposits"][0]["envelope"] == env


def test_drop_clears_record(handlers):
    deposit, fetch, drop, _, _ = handlers
    env = _envelope()
    reply = deposit({"type": "relay.deposit", "v": 1, "envelope": env}, ("peer", 0))
    deposit_id = reply["deposit_id"]
    drop(
        {
            "type": "relay.drop",
            "v": 1,
            "recipient_public_id": env["recipient_public_id"],
            "deposit_ids": [deposit_id],
        },
        ("peer", 0),
    )
    after = fetch(
        {
            "type": "relay.fetch",
            "v": 1,
            "recipient_public_id": env["recipient_public_id"],
            "limit": 64,
        },
        ("peer", 0),
    )
    assert after["deposits"] == []


def test_drop_other_recipient_is_no_op(handlers):
    deposit, _, drop, _, _ = handlers
    env = _envelope()
    reply = deposit({"type": "relay.deposit", "v": 1, "envelope": env}, ("peer", 0))
    deposit_id = reply["deposit_id"]
    res = drop(
        {
            "type": "relay.drop",
            "v": 1,
            "recipient_public_id": "narada1qsomeoneelse",
            "deposit_ids": [deposit_id],
        },
        ("peer", 0),
    )
    assert res["removed"] == 0
