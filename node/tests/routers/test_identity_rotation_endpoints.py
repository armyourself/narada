"""Tests for the Narada identity HTTP router rotation endpoints.

Tests the new rotate-x25519 and key-update endpoints.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.narada_identity.identity import (
    generate_identity,
    identity_from_keystore,
)
from src.narada_identity.keystore import InMemoryKeystore
from src.routers import narada_identity_tasks as router_module


def _make_client():
    """Build a FastAPI test client with the identity router."""
    # Reset the module-level keystore.
    router_module._keystore = None
    app = FastAPI()
    app.include_router(router_module.router)
    return TestClient(app)


class TestRotateX25519Endpoint:
    def test_rotate_x25519_success(self):
        client = _make_client()
        ks = InMemoryKeystore()
        router_module._keystore = ks

        # Generate first.
        resp = client.post("/narada/identity/generate", params={"account_id": "test@example.com"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        old_public_id = data["data"]["public_id"]

        # Rotate X25519.
        resp = client.post(
            "/Narada/identity/rotate-x25519",
            json={"account_id": "test@example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["x25519_preserved"] is True
        assert data["data"]["public_id"] != old_public_id
        assert "mnemonic_claim_token" in data["data"]

    def test_rotate_x25519_no_identity(self):
        client = _make_client()
        ks = InMemoryKeystore()
        router_module._keystore = ks

        resp = client.post(
            "/Narada/identity/rotate-x25519",
            json={"account_id": "nonexistent@example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_rotate_x25519_invalid_account_id(self):
        client = _make_client()
        ks = InMemoryKeystore()
        router_module._keystore = ks

        resp = client.post(
            "/Narada/identity/rotate-x25519",
            json={"account_id": "../../etc/passwd"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False


class TestKeyUpdateEndpoint:
    def test_key_update_success(self):
        client = _make_client()
        ks = InMemoryKeystore()
        router_module._keystore = ks

        # Generate identity.
        resp = client.post("/narada/identity/generate", params={"account_id": "sender@example.com"})
        assert resp.status_code == 200
        old_mnemonic = ""  # We need the mnemonic but the endpoint returns a claim token.

        # For the key-update endpoint, we need the OLD mnemonic.
        # Generate separately to capture it.
        ks2 = InMemoryKeystore()
        old_identity, old_mnemonic = generate_identity("sender@example.com", keystore=ks2)

        # Generate a recipient.
        recipient, _ = generate_identity("recipient@example.com", keystore=InMemoryKeystore())

        # Rotate to get a new identity in the main keystore.
        from src.narada_identity.identity import rotate_identity_preserve_x25519
        rotate_identity_preserve_x25519("sender@example.com", ks)
        router_module._keystore = ks

        # Build key-update envelope.
        resp = client.post(
            "/Narada/identity/key-update",
            json={
                "account_id": "sender@example.com",
                "recipient_public_id": recipient.public_id,
                "old_mnemonic": old_mnemonic,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        envelope = data["data"]["envelope"]
        assert envelope["v"] == 3
        assert envelope["sender_public_id"] == old_identity.public_id
        assert envelope["recipient_public_id"] == recipient.public_id

    def test_key_update_missing_old_mnemonic(self):
        client = _make_client()
        ks = InMemoryKeystore()
        router_module._keystore = ks

        resp = client.post("/narada/identity/generate", params={"account_id": "test@example.com"})
        recipient, _ = generate_identity("recipient@example.com", keystore=InMemoryKeystore())

        resp = client.post(
            "/Narada/identity/key-update",
            json={
                "account_id": "test@example.com",
                "recipient_public_id": recipient.public_id,
                "old_mnemonic": "",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "old_mnemonic is required" in data["message"]
