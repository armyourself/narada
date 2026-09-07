"""End-to-end relay path: Alice -> Relay -> Bob (Bob offline at send time).

Bob's home node is unknown to Alice's directory, so the direct path
fails. Alice's adapter consults :class:`RelaySelector` and hands the
envelope to the in-process relay. Bob comes back online, fetches from
the relay, and the existing inbox path verifies + decrypts +
persists the message.
"""

from __future__ import annotations

import secrets
import time
from pathlib import Path

from src.narada.adapter import NaradaAdapter
from src.narada.directory import InMemoryDirectory
from src.narada.envelope import NaradaEnvelope, open_envelope
from src.narada.outbox import Outbox
from src.narada.node_identity import NaradaNodeIdentity
from src.narada.p2p.listener import PeerBook, PeerState
from src.narada.relay.handlers import build_deposit_handler, build_fetch_handler
from src.narada.relay.receipt import verify_stored_receipt
from src.narada.relay.store import RelayStore
from src.narada.transport import NaradaTransport, NaradaTransportError
from src.narada_identity.identity import generate_identity
from src.narada_identity.keystore import InMemoryKeystore
from src.mail_abstraction import Address


class _RelayBridge:
    """In-process bridge between Alice's adapter and the relay.

    The adapter's ``relay_deposit`` hook expects ``(endpoint,
    envelope, ttl_seconds)``; the bridge dispatches to the relay's
    deposit handler in-process.
    """

    def __init__(self, store: RelayStore, relay_identity: NaradaNodeIdentity):
        self._store = store
        self._identity = relay_identity
        self._deposit = build_deposit_handler(
            store=store, relay_identity=relay_identity
        )
        self._fetch = build_fetch_handler(store=store)
        self._peer_table = PeerBook()

    def deposit(self, endpoint: str, envelope: dict, ttl_seconds=None) -> dict:
        return self._deposit(
            {"type": "relay.deposit", "v": 1, "envelope": envelope},
            ("alice", 0),
        )

    def fetch_for(self, recipient_public_id: str):
        return self._fetch(
            {
                "type": "relay.fetch",
                "v": 1,
                "recipient_public_id": recipient_public_id,
                "limit": 64,
            },
            ("bob", 0),
        )

    def peer_book(self) -> PeerBook:
        return self._peer_table


def test_send_to_unknown_recipient_deposits_at_relay(tmp_path: Path):
    ks = InMemoryKeystore()
    alice_identity, _ = generate_identity("alice@example.com", keystore=ks)
    bob_identity, _ = generate_identity("bob@example.com", keystore=ks)
    directory = InMemoryDirectory()
    outbox = Outbox(tmp_path / "narada")
    relay_store = RelayStore(tmp_path / "relay", master_key=secrets.token_bytes(32))
    relay_id = NaradaNodeIdentity.generate()
    bridge = _RelayBridge(relay_store, relay_id)

    # Alice has NO direct route to Bob: the directory knows only herself.
    transport = _LocalTransport()
    alice = NaradaAdapter(
        "alice@example.com",
        directory=directory,
        outbox=outbox,
        transport=transport,
        keystore=ks,
        data_dir=tmp_path,
    )
    peer_book = bridge.peer_book()
    state = PeerState(endpoint="relay.local:4440", node_id=relay_id.public_id)
    peer_book._peers[state.endpoint] = state
    alice.set_relay_peer_book(peer_book)
    alice.set_relay_deposit(bridge.deposit)

    ok, msg = alice.send_message(
        from_address=Address(address="alice@example.com", name="Alice"),
        to_addresses=[Address(address=bob_identity.public_id, name=None)],
        subject="offline hi",
        body="hello bob",
    )
    assert ok is True, msg
    assert "relay" in msg.lower()
    # Outbox is clean because the deposit succeeded.
    assert outbox.list_all("alice@example.com") == []

    # Bob is now online and pulls from the relay.
    reply = bridge.fetch_for(bob_identity.public_id)
    assert reply["type"] == "relay.fetch.result"
    assert len(reply["deposits"]) == 1
    stored = reply["deposits"][0]
    assert stored["envelope"]["sender_public_id"] == alice_identity.public_id
    assert stored["envelope"]["recipient_public_id"] == bob_identity.public_id

    # Bob opens the envelope locally with his own identity; the
    # existing inbox path validates + decrypts.
    body = open_envelope(NaradaEnvelope.from_dict(stored["envelope"]), bob_identity)
    assert body.subject == "offline hi"
    assert body.body_text == "hello bob"


def test_relay_deposit_receipt_is_signed(tmp_path: Path):
    """The relay.stored receipt must be signed by the relay."""
    ks = InMemoryKeystore()
    bob_identity, _ = generate_identity("bob@example.com", keystore=ks)
    relay_store = RelayStore(tmp_path / "relay", master_key=secrets.token_bytes(32))
    relay_id = NaradaNodeIdentity.generate()
    bridge = _RelayBridge(relay_store, relay_id)
    envelope = {
        "v": 1,
        "sender_public_id": "narada1alice...",
        "recipient_public_id": bob_identity.public_id,
        "message_id": secrets.token_hex(8),
        "timestamp": int(time.time()),
        "nonce": secrets.token_hex(16),
        "signature": secrets.token_hex(64),
        "body_ciphertext": secrets.token_hex(64),
    }
    reply = bridge.deposit("relay.local:4440", envelope)
    assert reply["type"] == "relay.stored"
    from src.narada.relay.receipt import StoredReceipt
    receipt = StoredReceipt.from_dict(reply)
    assert verify_stored_receipt(receipt, expected_message_id=envelope["message_id"])


class _LocalTransport(NaradaTransport):
    """A transport that does nothing (no direct peers)."""

    def send(self, recipient_base_url: str, envelope: dict) -> None:
        raise NaradaTransportError("no direct peers in test")

    def send_with_ack(self, recipient_base_url: str, envelope: dict):
        raise NaradaTransportError("no direct peers in test")
