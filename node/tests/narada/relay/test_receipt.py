"""Unit tests for :mod:`src.narada.relay.receipt`."""

from __future__ import annotations

import secrets
import time

from src.narada.node_identity import NaradaNodeIdentity
from src.narada.relay.receipt import (
    RECEIPT_VERSION,
    make_stored_receipt,
    verify_stored_receipt,
)

def test_receipt_round_trip():
    node = NaradaNodeIdentity.generate()
    receipt = make_stored_receipt(
        relay=node,
        deposit_id=secrets.token_hex(8),
        recipient_public_id="narada1qtest",
        message_id=secrets.token_hex(8),
        stored_at=int(time.time()),
        expires_at=int(time.time()) + 3600,
    )
    assert receipt.relay_node_id == node.public_id
    assert verify_stored_receipt(receipt) is True


def test_receipt_message_id_must_match():
    node = NaradaNodeIdentity.generate()
    receipt = make_stored_receipt(
        relay=node,
        deposit_id=secrets.token_hex(8),
        recipient_public_id="narada1qtest",
        message_id="m1",
        stored_at=1,
        expires_at=2,
    )
    assert verify_stored_receipt(receipt, expected_message_id="m1") is True
    assert verify_stored_receipt(receipt, expected_message_id="m2") is False


def test_receipt_tampered_signature_fails():
    node = NaradaNodeIdentity.generate()
    receipt = make_stored_receipt(
        relay=node,
        deposit_id=secrets.token_hex(8),
        recipient_public_id="narada1qtest",
        message_id="m1",
        stored_at=1,
        expires_at=2,
    )
    tampered = receipt.as_dict()
    tampered["expires_at"] = 9999
    # Re-parse; signature is now stale.
    from src.narada.relay.receipt import StoredReceipt
    bad = StoredReceipt.from_dict(tampered)
    assert verify_stored_receipt(bad) is False


def test_receipt_version_constant_is_one():
    assert RECEIPT_VERSION == 1
