"""Tests for the per-node Narada identity module."""

from __future__ import annotations

import json
from pathlib import Path

from src.narada_identity.encoding import decode_node_id, encode_node_id
from src.narada.node_identity import (
    NaradaNodeIdentity,
    load_or_create,
    verify_node_signature,
)


def test_generate_roundtrip():
    n = NaradaNodeIdentity.generate()
    assert n.public_id.startswith("node1")
    # decode and recover the same bytes
    ed_pub = decode_node_id(n.public_id)
    assert ed_pub == n.ed25519_public_bytes
    # bech32m encoding of the raw bytes must round-trip
    assert encode_node_id(n.ed25519_public_bytes) == n.public_id


def test_sign_verify_roundtrip():
    n = NaradaNodeIdentity.generate()
    msg = b"hello node"
    sig = n.sign(msg)
    assert len(sig) == 64
    assert verify_node_signature(n.public_id, sig, msg) is True


def test_verify_rejects_wrong_message():
    n = NaradaNodeIdentity.generate()
    sig = n.sign(b"a")
    assert verify_node_signature(n.public_id, sig, b"b") is False


def test_verify_rejects_wrong_node():
    n1 = NaradaNodeIdentity.generate()
    n2 = NaradaNodeIdentity.generate()
    sig = n1.sign(b"hi")
    # Signed by n1 but asserted to come from n2: must fail.
    assert verify_node_signature(n2.public_id, sig, b"hi") is False


def test_verify_rejects_malformed_id():
    # Garbage node ids must return False, never raise.
    assert verify_node_signature("not-a-node-id", b"\x00" * 64, b"hi") is False
    assert verify_node_signature("", b"\x00" * 64, b"hi") is False


def test_verify_rejects_bad_signature_length():
    n = NaradaNodeIdentity.generate()
    assert verify_node_signature(n.public_id, b"too short", b"hi") is False
    assert verify_node_signature(n.public_id, b"\x00" * 63, b"hi") is False


def test_from_seed_is_deterministic():
    seed = b"\x42" * 32
    a = NaradaNodeIdentity.from_seed(seed)
    b = NaradaNodeIdentity.from_seed(seed)
    assert a.public_id == b.public_id
    assert a.ed25519_public_bytes == b.ed25519_public_bytes


def test_load_or_create_persists_across_calls(tmp_path: Path):
    n1 = load_or_create(tmp_path)
    n2 = load_or_create(tmp_path)
    # Same on-disk seed must yield the same identity.
    assert n1.public_id == n2.public_id
    assert (tmp_path / "node_identity" / "seed").exists()


def test_load_or_create_ephemeral_does_not_persist(tmp_path: Path):
    n1 = load_or_create(tmp_path, ephemeral=True)
    n2 = load_or_create(tmp_path, ephemeral=True)
    # Ephemeral mode must produce fresh identities every time.
    assert n1.public_id != n2.public_id
    # And nothing was written to disk.
    assert not (tmp_path / "node_identity").exists()


def test_load_or_create_default_is_persistent(tmp_path: Path):
    n1 = load_or_create(tmp_path)
    seed_bytes = (tmp_path / "node_identity" / "seed").read_bytes()
    n2 = NaradaNodeIdentity.from_seed(seed_bytes)
    assert n1.public_id == n2.public_id


def test_envelope_dict_includes_node_fields(tmp_path: Path):
    # Just exercise the encoding helpers that node-identity envelopes use.
    n = NaradaNodeIdentity.generate()
    sig = n.sign(b"data")
    payload = {
        "sender_node_id": n.public_id,
        "sender_node_signature": sig.hex(),
    }
    # JSON round-trip preserves the bytes.
    rt = json.loads(json.dumps(payload))
    assert rt["sender_node_id"].startswith("node1")
    assert len(bytes.fromhex(rt["sender_node_signature"])) == 64