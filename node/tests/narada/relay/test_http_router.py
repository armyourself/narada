"""HTTP /narada/relay/{deposit,fetch,drop,sweep} round-trip."""

from __future__ import annotations

import secrets
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.narada.node_identity import NaradaNodeIdentity, load_or_create
from src.routers import narada_relay_tasks


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    narada_relay_tasks.reset_for_tests()
    narada_relay_tasks.configure(
        data_dir=tmp_path,
        master_key=secrets.token_bytes(32),
        node_identity=NaradaNodeIdentity.generate(),
    )
    app = FastAPI()
    app.include_router(narada_relay_tasks.router)
    return TestClient(app)


def _envelope(recipient: str) -> dict:
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


def test_http_deposit_returns_signed_receipt(client: TestClient):
    env = _envelope("narada1qtest")
    res = client.post("/narada/relay/deposit", json={"v": 1, "envelope": env})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["type"] == "relay.stored"
    assert body["recipient_public_id"] == env["recipient_public_id"]


def test_http_fetch_returns_only_owners_deposits(client: TestClient):
    env = _envelope("narada1qtest")
    client.post("/narada/relay/deposit", json={"v": 1, "envelope": env})
    res = client.post(
        "/narada/relay/fetch",
        json={
            "v": 1,
            "recipient_public_id": "narada1qtest",
            "limit": 64,
        },
    )
    body = res.json()
    assert body["type"] == "relay.fetch.result"
    assert len(body["deposits"]) == 1


def test_http_drop_clears(client: TestClient):
    env = _envelope("narada1qtest")
    res = client.post("/narada/relay/deposit", json={"v": 1, "envelope": env})
    deposit_id = res.json()["deposit_id"]
    drop = client.post(
        "/narada/relay/drop",
        json={
            "v": 1,
            "recipient_public_id": "narada1qtest",
            "deposit_ids": [deposit_id],
        },
    )
    assert drop.json()["removed"] == 1
    res = client.post(
        "/narada/relay/fetch",
        json={
            "v": 1,
            "recipient_public_id": "narada1qtest",
            "limit": 64,
        },
    )
    assert res.json()["deposits"] == []


def test_http_deposit_rejects_bad_recipient(client: TestClient):
    env = _envelope("not-a-valid-id")
    res = client.post("/narada/relay/deposit", json={"v": 1, "envelope": env})
    body = res.json()
    assert body["type"] == "error"


def test_http_sweep_runs(client: TestClient):
    res = client.post("/narada/relay/sweep")
    assert res.status_code == 200
    assert res.json()["type"] == "relay.sweep.result"
