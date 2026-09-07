"""Tests for the /narada/sync HTTP endpoint (Phase 3 commit 5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.internal.account_manager import Account, AccountManager
from src.narada_identity.identity import generate_identity
from src.narada_identity.keystore import InMemoryKeystore
from src.routers import narada_protocol_tasks as router_module


@pytest.fixture
def app_and_dirs(tmp_path: Path, monkeypatch):
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


def test_sync_get_returns_empty_when_no_mailbox(app_and_dirs):
    client, _alice, _bob, _tmp = app_and_dirs
    resp = client.get(
        "/narada/sync",
        params={"account_id": "alice@example.com", "since": 0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False  # unknown account_id (mailbox file missing)


def test_sync_post_with_empty_mailbox(app_and_dirs):
    client, _alice, _bob, _tmp = app_and_dirs
    resp = client.post(
        "/narada/sync",
        json={"account_id": "alice@example.com", "since": 0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False  # mailbox does not exist yet


def test_sync_returns_persisted_envelope_after_inbox_accept(app_and_dirs):
    """End-to-end: accept an envelope via /narada/inbox, then sync returns it."""
    from src.narada.envelope import NaradaBody, make_envelope

    client, alice, bob, tmp_path = app_and_dirs
    body = NaradaBody(subject="hello", body_text="world")
    envelope = make_envelope(alice, bob.public_id, body)
    accept = client.post("/narada/inbox", json=envelope.as_dict())
    assert accept.status_code == 200
    assert accept.json()["success"] is True

    # Now sync for bob.
    resp = client.get(
        "/narada/sync",
        params={"account_id": "bob@example.com", "since": 0},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    entries = payload["data"]["entries"]
    assert len(entries) == 1
    assert entries[0]["subject"] == "hello"
    assert entries[0]["sender_public_id"] == alice.public_id


def test_sync_since_filters_out_old_entries(app_and_dirs):
    """A sync with since=received_at of the most recent entry returns nothing."""
    from src.narada.envelope import NaradaBody, make_envelope

    client, alice, bob, _tmp = app_and_dirs
    body = NaradaBody(subject="hello")
    envelope = make_envelope(alice, bob.public_id, body)
    client.post("/narada/inbox", json=envelope.as_dict())

    first = client.get(
        "/narada/sync",
        params={"account_id": "bob@example.com", "since": 0},
    ).json()
    assert len(first["data"]["entries"]) == 1
    last_received_at = int(first["data"]["entries"][0]["received_at"])

    second = client.get(
        "/narada/sync",
        params={"account_id": "bob@example.com", "since": last_received_at},
    ).json()
    assert second["data"]["entries"] == []


def test_sync_invalid_account_id_rejected(app_and_dirs):
    client, _alice, _bob, _tmp = app_and_dirs
    resp = client.post(
        "/narada/sync",
        json={"account_id": "../etc/passwd", "since": 0},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert "account_id" in resp.json()["message"].lower()
