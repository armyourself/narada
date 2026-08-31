"""End-to-end tests for the LatticeAdapter (and InMemoryTransport)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.lattice.adapter import LatticeAdapter
from src.lattice.directory import InMemoryDirectory
from src.lattice.envelope import LatticeEnvelope
from src.lattice.outbox import Outbox
from src.lattice.transport import LatticeTransport, LatticeTransportError
from src.lattice_identity.identity import generate_identity
from src.lattice_identity.keystore import InMemoryKeystore
from src.mail_abstraction import Address, MailAdapterError


class InMemoryTransport(LatticeTransport):
    """A transport that delivers envelopes to an in-process inbox.

    Useful for tests: we avoid the HTTP roundtrip but exercise the
    full adapter -> transport -> adapter path.

    The transport routes by base_url: each adapter is associated with
    a base_url via a class-level registry. ``send(base_url, env)``
    delivers to the adapter registered under that base_url. This lets
    a single test wire multiple senders and receivers.
    """

    _REGISTRY: dict[str, "LatticeAdapter"] = {}

    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    @classmethod
    def register(cls, base_url: str, receiver: "LatticeAdapter") -> None:
        cls._REGISTRY[base_url] = receiver

    @classmethod
    def reset(cls) -> None:
        cls._REGISTRY.clear()

    def send(self, recipient_base_url: str, envelope: dict) -> None:
        self.sent.append((recipient_base_url, envelope))
        receiver = self._REGISTRY.get(recipient_base_url)
        if receiver is not None:
            receiver.deliver_for_test(envelope)


@pytest.fixture(autouse=True)
def _reset_transport_registry():
    InMemoryTransport.reset()
    yield
    InMemoryTransport.reset()


def _setup_two_nodes(tmp_path: Path):
    """Build Alice and Bob adapters sharing a directory + transport."""
    ks = InMemoryKeystore()
    alice_identity, _ = generate_identity("alice@example.com", keystore=ks)
    bob_identity, _ = generate_identity("bob@example.com", keystore=ks)

    directory = InMemoryDirectory()
    outbox = Outbox(tmp_path / "lattice")

    transport = InMemoryTransport()

    alice = LatticeAdapter(
        "alice@example.com",
        directory=directory,
        outbox=outbox,
        transport=transport,
        keystore=ks,
        data_dir=tmp_path,
    )
    bob = LatticeAdapter(
        "bob@example.com",
        directory=directory,
        outbox=outbox,
        transport=transport,
        keystore=ks,
        data_dir=tmp_path,
    )

    InMemoryTransport.register("mem://bob", bob)
    InMemoryTransport.register("mem://alice", alice)

    directory.add(bob_identity.public_id, "mem://bob", "bob@example.com")
    directory.add(alice_identity.public_id, "mem://alice", "alice@example.com")

    return alice, bob, transport, outbox, alice_identity, bob_identity


def test_send_message_delivers_to_recipient(tmp_path):
    alice, bob, _transport, outbox, _, bob_identity = _setup_two_nodes(tmp_path)
    ok, msg = alice.send_message(
        from_address=Address(address="alice@example.com", name="Alice"),
        to_addresses=[Address(address=bob_identity.public_id, name=None)],
        subject="hi",
        body="hello",
    )
    assert ok is True
    assert "delivered" in msg
    messages = bob.fetch_messages("Lattice", limit=10, offset=0)
    assert len(messages) == 1
    assert messages[0].subject == "hi"
    assert "hello" in (messages[0].preview or "")
    assert outbox.list_all("alice@example.com") == []


def test_send_message_unknown_recipient_queues_in_outbox(tmp_path):
    alice, _bob, _transport, outbox, _, _ = _setup_two_nodes(tmp_path)
    ks = InMemoryKeystore()
    stranger, _ = generate_identity("stranger@example.com", keystore=ks)
    ok, msg = alice.send_message(
        from_address=Address(address="alice@example.com"),
        to_addresses=[Address(address=stranger.public_id)],
        subject="hi",
        body="hello",
    )
    assert ok is False
    assert "outbox" in msg.lower()
    assert len(outbox.list_all("alice@example.com")) == 1


def test_send_message_failure_queues_with_backoff(tmp_path):
    alice, bob, transport, outbox, _, bob_identity = _setup_two_nodes(tmp_path)

    # Wrap the transport so the first send raises, then the second one
    # goes through normally.
    real_send = transport.send
    call_count = {"n": 0}

    def flaky_send(base_url, env):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise LatticeTransportError("simulated outage")
        return real_send(base_url, env)

    transport.send = flaky_send  # type: ignore[assignment]
    ok, msg = alice.send_message(
        from_address=Address(address="alice@example.com"),
        to_addresses=[Address(address=bob_identity.public_id)],
        subject="hi",
        body="hello",
    )
    assert ok is False
    assert len(outbox.list_all("alice@example.com")) == 1

    # Force the entry to be due now so the drainer can pick it up. We
    # mutate the OutboxEntry's next_attempt_at directly via re-enqueue
    # to bypass the backoff.
    entries = outbox.list_all("alice@example.com")
    assert len(entries) == 1
    outbox.remove("alice@example.com", entries[0].message_id)
    outbox.enqueue(
        account_id="alice@example.com",
        recipient_public_id=bob_identity.public_id,
        envelope=entries[0].envelope,
        first_attempt_delay_seconds=0,
    )

    sent_count = alice.drain_outbox(max_per_account=8)
    assert sent_count == 1
    messages = bob.fetch_messages("Lattice", limit=10, offset=0)
    assert len(messages) == 1


def test_fetch_messages_returns_empty_for_unknown_account(tmp_path):
    alice, _bob, _transport, _outbox, _, _ = _setup_two_nodes(tmp_path)
    assert alice.fetch_messages("Lattice", limit=10, offset=0) == []


def test_list_folders(tmp_path):
    alice, _bob, _transport, _outbox, _, _ = _setup_two_nodes(tmp_path)
    folders = alice.list_folders()
    assert len(folders) == 1
    assert folders[0].name == "Lattice"


def test_watch_not_implemented(tmp_path):
    alice, _bob, _transport, _outbox, _, _ = _setup_two_nodes(tmp_path)
    with pytest.raises(MailAdapterError):
        alice.watch("Lattice", lambda m: None)


def test_send_message_multi_recipient(tmp_path):
    alice, bob, transport, outbox, _, bob_identity = _setup_two_nodes(tmp_path)
    # Add a third node (Carol).
    ks = InMemoryKeystore()
    carol_identity, _ = generate_identity("carol@example.com", keystore=ks)
    carol = LatticeAdapter(
        "carol@example.com",
        directory=alice.directory,
        outbox=outbox,
        transport=transport,
        keystore=ks,
        data_dir=tmp_path,
    )
    InMemoryTransport.register("mem://carol", carol)
    alice.directory.add(carol_identity.public_id, "mem://carol", "carol@example.com")

    ok, msg = alice.send_message(
        from_address=Address(address="alice@example.com"),
        to_addresses=[
            Address(address=bob_identity.public_id),
            Address(address=carol_identity.public_id),
        ],
        subject="hi all",
        body="hello",
    )
    assert ok is True
    assert bob.fetch_messages("Lattice", limit=10, offset=0)
    assert carol.fetch_messages("Lattice", limit=10, offset=0)
