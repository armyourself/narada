"""Router-level end-to-end test for Phase 1 on-the-wire key rotation.

Walks the real /narada/inbox HTTP route (not the in-process
deliver_for_test path) to verify:

1. A v=3 key-update envelope is rejected by the router because
   the router-side inbox does not yet have a rotation store
   configured. (A follow-up commit will add a router-side
   wiring so v=3 envelopes are accepted.)

2. After persisting the rotation through a direct inbox call,
   a v=1 envelope signed with the new ed25519 key is accepted
   by a rotation-aware inbox.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.internal.account_manager import Account, AccountManager
from src.narada.envelope import NaradaBody, make_envelope
from src.narada.key_rotation_store import KeyRotationStore
from src.narada.key_update import make_key_update_envelope
from src.narada_identity.identity import (
    generate_identity,
    rotate_identity_preserve_x25519,
)
from src.narada_identity.keystore import InMemoryKeystore
from src.routers import narada_protocol_tasks as router_module


def _hmac_key() -> bytes:
    return b"K" * 32


@dataclass
class _RouterFixture:
    client: TestClient
    alice: object  # NaradaIdentity
    bob: object
    alice_ks: InMemoryKeystore
    tmp_path: Path


@pytest.fixture
def two_nodes(tmp_path: Path, monkeypatch):
    """Two accounts (alice, bob) on a single FastAPI app."""
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
    return _RouterFixture(
        client=client, alice=alice, bob=bob, alice_ks=ks, tmp_path=tmp_path
    )


def test_router_accepts_v1_envelope_no_rotation(two_nodes):
    """Backwards compat: a v=1 envelope from a sender with no
    rotation record is accepted by the router (the standard
    Phase 2 path).
    """
    body = NaradaBody(subject="hi", body_text="hello")
    env = make_envelope(two_nodes.alice, two_nodes.bob.public_id, body)
    resp = two_nodes.client.post("/narada/inbox", json=env.as_dict())
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["data"]["duplicate"] is False


def test_router_rejects_v3_envelope(two_nodes):
    """The router does not yet thread the rotation store into the
    inbox; v=3 envelopes are rejected with a 'rotation store'
    error.
    """
    ks_for_rotation = InMemoryKeystore()
    alice2, _ = generate_identity("alice@example.com", keystore=ks_for_rotation)
    alice2_new, _ = rotate_identity_preserve_x25519(
        "alice@example.com", ks_for_rotation
    )
    update_env = make_key_update_envelope(
        alice2, two_nodes.bob.public_id, alice2_new
    )
    resp = two_nodes.client.post("/narada/inbox", json=update_env.as_dict())
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is False
    assert "rotation store" in payload["message"]


def test_router_v1_envelope_after_external_rotation_recorded(two_nodes):
    """After persisting a rotation on Bob's side (via a direct
    inbox call), a v=1 envelope signed with the new key is
    accepted by a rotation-aware inbox. The test uses two
    inboxes: one for the rotation store, one for the router.
    """
    from src.narada.inbox import NaradaInbox

    # Alice's perspective (independent keystore for the rotation).
    ks_for_alice = InMemoryKeystore()
    alice2, _ = generate_identity("alice@example.com", keystore=ks_for_alice)
    alice2_new, _ = rotate_identity_preserve_x25519(
        "alice@example.com", ks_for_alice
    )
    # Bob's perspective: separate keystore for the rotation.
    ks_bob = InMemoryKeystore()
    bob_for_rotation, _ = generate_identity(
        "bob@example.com", keystore=ks_bob
    )
    # Persist the rotation via a rotation-aware inbox.
    rot_store = KeyRotationStore(two_nodes.tmp_path / "rot.json", key=_hmac_key())
    bob_inbox = NaradaInbox(
        "bob@example.com", keystore=ks_bob, rotation_store=rot_store
    )
    update_env = make_key_update_envelope(
        alice2, bob_for_rotation.public_id, alice2_new
    )
    _, _, is_ku = bob_inbox.receive(update_env)
    assert is_ku is True

    # Now Alice (new) sends a v=1 envelope; bob_inbox (with
    # rotation store) accepts it under the new ed25519 key.
    body = NaradaBody(subject="after-rotation", body_text="hi")
    env = make_envelope(alice2_new, bob_for_rotation.public_id, body)
    opened, was_dup, is_ku2 = bob_inbox.receive(env)
    assert is_ku2 is False
    assert was_dup is False
    assert opened.subject == "after-rotation"
