"""Tests for ack timestamp-freshness window (threat T6)."""

from __future__ import annotations

import pytest

from src.narada.ack import (
    DEFAULT_ACK_MAX_AGE_SECONDS,
    make_ack,
    verify_ack,
)
from src.narada.node_identity import NaradaNodeIdentity


def test_fresh_ack_accepted():
    n = NaradaNodeIdentity.generate()
    ack = make_ack(n, "a", "b", "m1", timestamp=1_000_000)
    assert verify_ack(
        ack,
        expected_sender_public_id="a",
        expected_recipient_public_id="b",
        expected_message_id="m1",
        now=1_000_000 + 60,
    ) is True


def test_old_ack_rejected():
    """An ack older than the freshness window must be rejected (T6)."""
    n = NaradaNodeIdentity.generate()
    ack = make_ack(n, "a", "b", "m1", timestamp=1_000_000)
    # 10 minutes later, well past the 5-minute default window.
    assert verify_ack(
        ack,
        expected_sender_public_id="a",
        expected_recipient_public_id="b",
        expected_message_id="m1",
        now=1_000_000 + 10 * 60,
    ) is False


def test_future_ack_rejected():
    """An ack dated in the future is rejected (clock skew defence)."""
    n = NaradaNodeIdentity.generate()
    ack = make_ack(n, "a", "b", "m1", timestamp=1_000_000)
    # 10 minutes in the future.
    assert verify_ack(
        ack,
        expected_sender_public_id="a",
        expected_recipient_public_id="b",
        expected_message_id="m1",
        now=1_000_000 - 10 * 60,
    ) is False


def test_custom_max_age():
    n = NaradaNodeIdentity.generate()
    ack = make_ack(n, "a", "b", "m1", timestamp=1_000_000)
    # 60s old; accept with max_age=120, reject with max_age=30.
    assert verify_ack(
        ack,
        expected_sender_public_id="a",
        expected_recipient_public_id="b",
        expected_message_id="m1",
        now=1_000_000 + 60,
        max_age_seconds=120,
    ) is True
    assert verify_ack(
        ack,
        expected_sender_public_id="a",
        expected_recipient_public_id="b",
        expected_message_id="m1",
        now=1_000_000 + 60,
        max_age_seconds=30,
    ) is False


def test_default_max_age_is_five_minutes():
    assert DEFAULT_ACK_MAX_AGE_SECONDS == 300
