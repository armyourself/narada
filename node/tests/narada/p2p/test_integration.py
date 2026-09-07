"""End-to-end integration smoke for Phase 3 (commit 9).

Spins up two node data directories in a tmp dir, generates identities
for Alice and Bob, has Alice send an envelope to Bob through the
HTTP /narada/inbox endpoint, and verifies:

1. Bob's mailbox contains the envelope.
2. /narada/sync returns the envelope with the correct shape.
3. The per-sender watermark is updated to the envelope's
   received_at timestamp.
4. A second /narada/sync with since=last_received_at returns nothing.

This test does not exercise QUIC stream I/O; it uses the same HTTP
path that a remote QUIC sender's push channel would land at. The
listener's stream I/O is covered by the unit tests in test_listener.py.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.internal.account_manager import Account, AccountManager
from src.narada.envelope import NaradaBody, make_envelope
from src.narada_identity.identity import generate_identity
from src.narada_identity.keystore import InMemoryKeystore
from src.routers import narada_protocol_tasks as router_module


@pytest.fixture
def two_nodes(tmp_path: Path, monkeypatch):
    """Two accounts (alice, bob) on a single FastAPI app with a fresh tmp dir."""
    ks = InMemoryKeystore()
    alice, _ = generate_identity("alice@example.com", keystore=ks)
    bob, _ = generate_identity("bob@example.com", keystore=ks)

    manager = AccountManager()
    manager.remove_all()
    manager.add(
        Account(email_address="alice@example.com", narada_identity_id=alice.public_id)
    )
    manager.add(
        Account(email_address="bob@example.com", narada_identity_id=bob.public_id)
    )

    monkeypatch.setattr(router_module, "_keystore_factory", lambda: ks)
    monkeypatch.setattr(router_module, "_data_dir_factory", lambda: tmp_path)

    app = FastAPI()
    app.include_router(router_module.router)
    client = TestClient(app)
    return client, alice, bob, tmp_path


def test_two_node_end_to_end(two_nodes):
    client, alice, bob, tmp_path = two_nodes

    # Alice -> Bob.
    body = NaradaBody(
        subject="hello bob", body_text="e2e smoke", to=("bob@example.com",)
    )
    envelope = make_envelope(alice, bob.public_id, body)

    # Inbox accept (this is what a remote QUIC sender's stream handler
    # would call into).
    accept = client.post("/narada/inbox", json=envelope.as_dict())
    assert accept.status_code == 200
    payload = accept.json()
    assert payload["success"] is True
    assert payload["data"]["message_id"] == envelope.message_id
    assert payload["data"]["duplicate"] is False

    # Bob's mailbox exists.
    mailbox = tmp_path / "etc" / "mailbox.bob@example.com.jsonl"
    assert mailbox.exists()
    text = mailbox.read_text(encoding="utf-8")
    assert envelope.message_id in text
    assert "hello bob" in text

    # Sync returns the entry.
    sync = client.get(
        "/narada/sync",
        params={"account_id": "bob@example.com", "since": 0},
    )
    assert sync.status_code == 200
    body_data = sync.json()
    assert body_data["success"] is True
    entries = body_data["data"]["entries"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["subject"] == "hello bob"
    assert entry["body"] == "e2e smoke"
    assert entry["sender_public_id"] == alice.public_id
    last_received_at = int(entry["received_at"])

    # Watermark file was written.
    wm = tmp_path / "watermarks.json"
    assert wm.exists()
    import json

    wm_data = json.loads(wm.read_text())
    assert int(wm_data.get(alice.public_id, -1)) == last_received_at

    # Second sync since=last_received_at returns nothing.
    second = client.get(
        "/narada/sync",
        params={"account_id": "bob@example.com", "since": last_received_at},
    )
    assert second.status_code == 200
    assert second.json()["data"]["entries"] == []


def test_two_node_ack_signed_by_node_identity(two_nodes):
    """Successful inbox accept returns an ack signed by Bob's node key."""
    from src.narada.ack import verify_ack
    from src.narada.node_identity import load_or_create

    client, alice, bob, tmp_path = two_nodes
    body = NaradaBody(subject="x")
    envelope = make_envelope(alice, bob.public_id, body)
    accept = client.post("/narada/inbox", json=envelope.as_dict())
    ack_dict = accept.json()["data"]["ack"]
    assert ack_dict is not None
    from src.narada.ack import NaradaAck

    ack = NaradaAck.from_dict(ack_dict)
    node = load_or_create(tmp_path)
    assert verify_ack(
        ack,
        expected_sender_public_id=alice.public_id,
        expected_recipient_public_id=bob.public_id,
        expected_message_id=envelope.message_id,
    ) is True
    assert ack.node_id == node.public_id


def test_two_node_replay_returns_duplicate(two_nodes):
    client, alice, bob, _tmp = two_nodes
    body = NaradaBody(subject="x")
    envelope = make_envelope(alice, bob.public_id, body)
    r1 = client.post("/narada/inbox", json=envelope.as_dict())
    r2 = client.post("/narada/inbox", json=envelope.as_dict())
    assert r1.json()["data"]["duplicate"] is False
    assert r2.json()["data"]["duplicate"] is True
