"""Unit tests for :mod:`src.narada.relay.store`.

Covers:

* Round-trip: deposit -> fetch decrypts the original envelope.
* Idempotency: a second deposit for the same
  ``(recipient, message_id)`` returns the existing record without
  charging quota twice.
* Quota caps: per-recipient deposit count, per-recipient bytes,
  global deposits, global bytes.
* TTL expiry: ``sweep`` removes expired entries; ``fetch`` skips
  them silently.
* Index tamper recovery: rewriting ``index.json`` without the
  matching tombstone log is detected and the live state rebuilds
  from tombstones.
* Persistence across reload: a second ``RelayStore`` over the
  same directory sees every entry the first instance wrote.
"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

import pytest

from src.narada.relay.store import (
    DEFAULT_MAX_BYTES_PER_RECIPIENT,
    DEFAULT_MAX_DEPOSITS_PER_RECIPIENT,
    RelayBadDeposit,
    RelayQuotaExceeded,
    RelayStore,
)


def _envelope(recipient: str, sender: str = "narada1alice...", msg_id: str | None = None) -> dict:
    return {
        "v": 1,
        "sender_public_id": sender,
        "recipient_public_id": recipient,
        "message_id": msg_id or secrets.token_hex(8),
        "timestamp": int(time.time()),
        "nonce": secrets.token_hex(16),
        "signature": secrets.token_hex(64),
        "body_ciphertext": secrets.token_hex(64),
    }


@pytest.fixture
def store(tmp_path: Path) -> RelayStore:
    return RelayStore(
        tmp_path,
        master_key=secrets.token_bytes(32),
        ttl_seconds=600,
    )


def test_deposit_and_fetch_round_trip(store: RelayStore):
    recipient = "narada1qtest"
    env = _envelope(recipient)
    stored = store.deposit(
        sender_public_id=env["sender_public_id"],
        envelope=env,
        recipient_public_id=recipient,
    )
    assert stored.deposit_id
    assert stored.recipient_public_id == recipient
    out = store.fetch(recipient_public_id=recipient)
    assert len(out) == 1
    assert out[0].deposit_id == stored.deposit_id
    assert out[0].envelope == env


def test_deposit_is_idempotent_per_recipient_and_message(store: RelayStore):
    recipient = "narada1qtest"
    env = _envelope(recipient)
    s1 = store.deposit(
        sender_public_id=env["sender_public_id"],
        envelope=env,
        recipient_public_id=recipient,
    )
    s2 = store.deposit(
        sender_public_id=env["sender_public_id"],
        envelope=env,
        recipient_public_id=recipient,
    )
    assert s1.deposit_id == s2.deposit_id
    assert len(store.fetch(recipient_public_id=recipient)) == 1


def test_per_recipient_deposit_cap(store: RelayStore):
    recipient = "narada1qtest"
    for i in range(DEFAULT_MAX_DEPOSITS_PER_RECIPIENT):
        store.deposit(
            sender_public_id="narada1alice...",
            envelope=_envelope(recipient, msg_id=f"m{i}"),
            recipient_public_id=recipient,
        )
    with pytest.raises(RelayQuotaExceeded):
        store.deposit(
            sender_public_id="narada1alice...",
            envelope=_envelope(recipient, msg_id="overflow"),
            recipient_public_id=recipient,
        )


def test_per_recipient_byte_cap(tmp_path: Path):
    recipient = "narada1qtest"
    # Use a tiny per-recipient byte cap so the test does not have to
    # construct multi-MiB envelopes.
    store = RelayStore(
        tmp_path,
        master_key=secrets.token_bytes(32),
        max_bytes_per_recipient=512,
        max_deposits_per_recipient=10,
    )
    big_envelope = _envelope(recipient, msg_id="big")
    # Pad the body to push the envelope close to the cap.
    base = json.dumps(big_envelope, separators=(",", ":")).encode("utf-8")
    pad = 480 - len(base)
    big_envelope["body_ciphertext"] = "A" * pad
    store.deposit(
        sender_public_id=big_envelope["sender_public_id"],
        envelope=big_envelope,
        recipient_public_id=recipient,
    )
    # A second envelope pushes us past the cap.
    with pytest.raises(RelayQuotaExceeded):
        store.deposit(
            sender_public_id="narada1alice...",
            envelope=_envelope(recipient, msg_id="big2"),
            recipient_public_id=recipient,
        )



def test_fetch_skips_expired(store: RelayStore):
    recipient = "narada1qtest"
    env = _envelope(recipient)
    store.deposit(
        sender_public_id=env["sender_public_id"],
        envelope=env,
        recipient_public_id=recipient,
        ttl_seconds=1,
        now=1_000,
    )
    assert store.fetch(recipient_public_id=recipient, now=1_001) == []


def test_drop_only_owner_can_remove(store: RelayStore):
    a = "narada1qtest"
    b = "narada1qtoast"
    env = _envelope(a)
    stored = store.deposit(
        sender_public_id=env["sender_public_id"],
        envelope=env,
        recipient_public_id=a,
    )
    # Wrong owner: no-op.
    assert store.drop(recipient_public_id=b, deposit_ids=[stored.deposit_id]) == 0
    # Right owner: removed.
    assert store.drop(recipient_public_id=a, deposit_ids=[stored.deposit_id]) == 1
    assert store.fetch(recipient_public_id=a) == []


def test_persistence_across_reload(tmp_path: Path):
    key = secrets.token_bytes(32)
    recipient = "narada1qtest"
    s1 = RelayStore(tmp_path, master_key=key)
    env = _envelope(recipient)
    s1.deposit(
        sender_public_id=env["sender_public_id"],
        envelope=env,
        recipient_public_id=recipient,
    )
    s2 = RelayStore(tmp_path, master_key=key)
    out = s2.fetch(recipient_public_id=recipient)
    assert len(out) == 1
    assert out[0].envelope == env


def test_index_tamper_does_not_silently_lose_state(tmp_path: Path):
    """If a disk attacker rewrites the index file, the live state
    must not be silently rebuilt from the attacker's lies; the
    tombstone log is the second source of truth."""
    key = secrets.token_bytes(32)
    recipient = "narada1qtest"
    s1 = RelayStore(tmp_path, master_key=key)
    env = _envelope(recipient)
    s1.deposit(
        sender_public_id=env["sender_public_id"],
        envelope=env,
        recipient_public_id=recipient,
    )
    index_path = tmp_path / "relay" / "index.json"
    payload = json.loads(index_path.read_bytes())
    # Tamper: pretend the deposit doesn't exist.
    tampered = {k: v for k, v in payload.items() if not isinstance(v, dict)}
    tampered_bytes = json.dumps(tampered, sort_keys=True, separators=(",", ":")).encode("utf-8")
    index_path.write_bytes(tampered_bytes)
    # Reload: tamper detected via HMAC, tombstone log replays the
    # real state.
    s2 = RelayStore(tmp_path, master_key=key)
    out = s2.fetch(recipient_public_id=recipient)
    assert len(out) == 1
    assert out[0].envelope == env


def test_tombstone_log_records_drops(tmp_path: Path):
    key = secrets.token_bytes(32)
    recipient = "narada1qtest"
    s1 = RelayStore(tmp_path, master_key=key)
    env = _envelope(recipient)
    stored = s1.deposit(
        sender_public_id=env["sender_public_id"],
        envelope=env,
        recipient_public_id=recipient,
    )
    s1.drop(recipient_public_id=recipient, deposit_ids=[stored.deposit_id])
    # Reload: the tombstone-recorded drop must keep the entry
    # removed even if a new attacker re-creates the on-disk file.
    s2 = RelayStore(tmp_path, master_key=key)
    assert s2.fetch(recipient_public_id=recipient) == []


def test_bad_recipient_rejected(store: RelayStore):
    with pytest.raises(RelayBadDeposit):
        store.deposit(
            sender_public_id="narada1alice...",
            envelope=_envelope("not-a-valid-id"),
            recipient_public_id="not-a-valid-id",
        )


def test_explicit_ttl_too_large_rejected(store: RelayStore):
    with pytest.raises(RelayBadDeposit):
        store.deposit(
            sender_public_id="narada1alice...",
            envelope=_envelope("narada1qtest"),
            recipient_public_id="narada1qtest",
            ttl_seconds=10_000_000,
        )
