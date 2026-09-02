"""Tests for the delivery-acknowledgement module."""

from __future__ import annotations

import json

from src.narada.ack import (
    ACK_STATUS_DELIVERED,
    ACK_VERSION,
    NaradaAck,
    NaradaAckError,
    make_ack,
    verify_ack,
)
from src.narada.node_identity import NaradaNodeIdentity


def test_make_ack_roundtrip():
    node = NaradaNodeIdentity.generate()
    ack = make_ack(
        node,
        sender_public_id="narada1abcdef",
        recipient_public_id="narada1ghijkl",
        message_id="msg-1",
    )
    assert ack.status == ACK_STATUS_DELIVERED
    assert ack.v == ACK_VERSION
    assert ack.node_id == node.public_id
    assert ack.signature and len(ack.signature) == 64
    # verify_ack with the right envelope details must accept it.
    assert verify_ack(
        ack,
        expected_sender_public_id="narada1abcdef",
        expected_recipient_public_id="narada1ghijkl",
        expected_message_id="msg-1",
    ) is True


def test_verify_ack_rejects_wrong_message_id():
    node = NaradaNodeIdentity.generate()
    ack = make_ack(
        node, "narada1aa", "narada1bb", "msg-1", status=ACK_STATUS_DELIVERED
    )
    assert verify_ack(
        ack,
        expected_sender_public_id="narada1aa",
        expected_recipient_public_id="narada1bb",
        expected_message_id="msg-2",
    ) is False


def test_verify_ack_rejects_wrong_recipient():
    node = NaradaNodeIdentity.generate()
    ack = make_ack(
        node, "narada1aa", "narada1bb", "msg-1", status=ACK_STATUS_DELIVERED
    )
    assert verify_ack(
        ack,
        expected_sender_public_id="narada1aa",
        expected_recipient_public_id="narada1cc",
        expected_message_id="msg-1",
    ) is False


def test_verify_ack_rejects_wrong_sender():
    node = NaradaNodeIdentity.generate()
    ack = make_ack(
        node, "narada1aa", "narada1bb", "msg-1", status=ACK_STATUS_DELIVERED
    )
    assert verify_ack(
        ack,
        expected_sender_public_id="narada1xx",
        expected_recipient_public_id="narada1bb",
        expected_message_id="msg-1",
    ) is False


def test_verify_ack_rejects_tampered_signature():
    node = NaradaNodeIdentity.generate()
    ack = make_ack(
        node, "narada1aa", "narada1bb", "msg-1", status=ACK_STATUS_DELIVERED
    )
    # Flip a single byte in the signature.
    tampered = NaradaAck(
        v=ack.v,
        sender_public_id=ack.sender_public_id,
        recipient_public_id=ack.recipient_public_id,
        message_id=ack.message_id,
        timestamp=ack.timestamp,
        status=ack.status,
        node_id=ack.node_id,
        signature=bytes(ack.signature[i] ^ (0xFF if i == 0 else 0) for i in range(len(ack.signature))),
    )
    assert verify_ack(
        tampered,
        expected_sender_public_id="narada1aa",
        expected_recipient_public_id="narada1bb",
        expected_message_id="msg-1",
    ) is False


def test_verify_ack_rejects_wrong_node_id():
    n1 = NaradaNodeIdentity.generate()
    n2 = NaradaNodeIdentity.generate()
    ack = make_ack(
        n1, "narada1aa", "narada1bb", "msg-1", status=ACK_STATUS_DELIVERED
    )
    # Swap the node_id so it claims to be from n2 but was signed by n1.
    swapped = NaradaAck(
        v=ack.v,
        sender_public_id=ack.sender_public_id,
        recipient_public_id=ack.recipient_public_id,
        message_id=ack.message_id,
        timestamp=ack.timestamp,
        status=ack.status,
        node_id=n2.public_id,
        signature=ack.signature,
    )
    assert verify_ack(
        swapped,
        expected_sender_public_id="narada1aa",
        expected_recipient_public_id="narada1bb",
        expected_message_id="msg-1",
    ) is False


def test_ack_as_dict_from_dict():
    node = NaradaNodeIdentity.generate()
    ack = make_ack(
        node, "narada1aa", "narada1bb", "msg-1", status=ACK_STATUS_DELIVERED
    )
    # JSON round-trip preserves signature bytes (base64 encoded).
    j = json.dumps(ack.as_dict())
    rt = NaradaAck.from_dict(json.loads(j))
    assert rt == ack


def test_ack_from_dict_rejects_garbage():
    try:
        NaradaAck.from_dict("not a dict")  # type: ignore[arg-type]
        assert False, "expected NaradaAckError"
    except NaradaAckError:
        pass


def test_ack_from_dict_rejects_missing_signature():
    try:
        NaradaAck.from_dict(
            {
                "v": 1,
                "sender_public_id": "x",
                "recipient_public_id": "y",
                "message_id": "z",
                "timestamp": 0,
                "status": ACK_STATUS_DELIVERED,
                "node_id": "node1...",
            }
        )
        assert False, "expected NaradaAckError"
    except NaradaAckError:
        pass


def test_make_ack_rejects_unknown_status():
    node = NaradaNodeIdentity.generate()
    try:
        make_ack(node, "a", "b", "c", status="bogus")
        assert False, "expected NaradaAckError"
    except NaradaAckError:
        pass