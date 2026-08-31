"""Tests for the Lattice protocol HTTP router."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.lattice.envelope import LatticeBody, make_envelope
from src.lattice_identity.identity import generate_identity
from src.lattice_identity.keystore import InMemoryKeystore
from src.routers import lattice_protocol_tasks as router_module


@pytest.fixture
def app_and_keystore(tmp_path: Path, monkeypatch):
    """Build a test app with an in-memory keystore and per-account inbox file."""
    ks = InMemoryKeystore()
    alice, _ = generate_identity("alice@example.com", keystore=ks)
    bob, _ = generate_identity("bob@example.com", keystore=ks)
    # Link Bob's public id to his account via the AccountManager so
    # the router can resolve recipient -> account_id. The
    # AccountManager is a process-wide singleton; we reset it first
    # so previous-test state doesn't leak in.
    from src.internal.account_manager import Account, AccountManager
    manager = AccountManager()
    manager.remove_all()
    manager.add(
        Account(
            email_address="bob@example.com",
            lattice_identity_id=bob.public_id,
        )
    )

    # Patch the router's default_keystore so the in-memory keystore
    # is used (the real default_keystore would point at the OS
    # keyring, which has no entry for our test account).
    from src.routers import lattice_protocol_tasks as router
    monkeypatch.setattr(router, "_keystore_factory", lambda: ks)
    monkeypatch.setattr(router, "_data_dir_factory", lambda: tmp_path)

    app = FastAPI()
    app.include_router(router.router)
    client = TestClient(app)

    return client, alice, bob, ks, tmp_path


def test_post_lattice_inbox_happy_path(app_and_keystore):
    client, alice, bob, _ks, _tmp = app_and_keystore
    body = LatticeBody(subject="hi", body_text="hello", to=("bob@example.com",))
    envelope = make_envelope(alice, bob.public_id, body)
    resp = client.post("/lattice/inbox", json=envelope.as_dict())
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["message_id"] == envelope.message_id
    assert data["data"]["duplicate"] is False


def test_post_lattice_inbox_rejects_tampered(app_and_keystore):
    client, alice, bob, _ks, _tmp = app_and_keystore
    body = LatticeBody(subject="hi")
    envelope = make_envelope(alice, bob.public_id, body)
    bad = envelope.as_dict()
    # Tamper with the ciphertext.
    raw = bytearray(__import__("base64").b64decode(bad["body_ciphertext"]))
    raw[-1] ^= 0xFF
    bad["body_ciphertext"] = __import__("base64").b64encode(bytes(raw)).decode("ascii")
    resp = client.post("/lattice/inbox", json=bad)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "rejected" in data["message"].lower()


def test_post_lattice_inbox_rejects_old_timestamp(app_and_keystore):
    client, alice, bob, _ks, _tmp = app_and_keystore
    body = LatticeBody(subject="hi")
    old = int(time.time()) - 3600
    envelope = make_envelope(alice, bob.public_id, body, timestamp=old)
    resp = client.post("/lattice/inbox", json=envelope.as_dict())
    assert resp.status_code == 200
    assert resp.json()["success"] is False


def test_post_lattice_inbox_rejects_unknown_recipient(app_and_keystore):
    client, _alice, _bob, _ks, _tmp = app_and_keystore
    # Build an envelope that targets a public id no local account has.
    # The sender can be anyone; the rejection is on the recipient side.
    from src.lattice_identity.keystore import InMemoryKeystore
    from src.lattice_identity.identity import generate_identity
    from src.lattice.envelope import make_envelope, LatticeBody
    ks2 = InMemoryKeystore()
    ghost, _ = generate_identity("ghost@example.com", keystore=ks2)
    # Find a public id that is NOT in the test fixture's account list.
    # We use ghost's own public id as the recipient, which is not
    # linked to any local account.
    body = LatticeBody(subject="hi")
    envelope = make_envelope(ghost, ghost.public_id, body)
    resp = client.post("/lattice/inbox", json=envelope.as_dict())
    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert "no local account" in resp.json()["message"].lower()


def test_post_lattice_inbox_idempotent(app_and_keystore):
    client, alice, bob, _ks, _tmp = app_and_keystore
    body = LatticeBody(subject="hi")
    envelope = make_envelope(alice, bob.public_id, body)
    resp1 = client.post("/lattice/inbox", json=envelope.as_dict())
    resp2 = client.post("/lattice/inbox", json=envelope.as_dict())
    assert resp1.json()["data"]["duplicate"] is False
    assert resp2.json()["data"]["duplicate"] is True


def test_get_lattice_inbox_listing(app_and_keystore):
    client, alice, bob, _ks, _tmp = app_and_keystore
    body = LatticeBody(subject="hello", body_text="body text")
    envelope = make_envelope(alice, bob.public_id, body)
    client.post("/lattice/inbox", json=envelope.as_dict())
    resp = client.get("/lattice/inbox/bob@example.com")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["data"]["messages"]) >= 1
    msg = body["data"]["messages"][0]
    assert msg["subject"] == "hello"
    assert msg["source"] == "lattice"


def test_outbox_retry_validates_account_id(app_and_keystore):
    client, _alice, _bob, _ks, _tmp = app_and_keystore
    resp = client.post("/lattice/outbox/retry", json={"account_id": "../etc/passwd"})
    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert "account_id" in resp.json()["message"].lower()
