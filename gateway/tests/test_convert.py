"""Unit tests for :mod:`gateway.gateway.convert`."""

from __future__ import annotations

import email.utils
from email.message import EmailMessage

import pytest

from gateway.gateway.convert import (
    narada_body_to_rfc822,
    rfc822_to_narada_body,
)
from gateway.gateway.errors import ConversionError


def test_round_trip_preserves_subject_and_body(alice_narada_id, bob_narada_id):
    body = {
        "subject": "hello",
        "sender": f"Alice <{alice_narada_id}>",
        "to": [bob_narada_id],
        "cc": [],
        "body_text": "hi bob",
        "sent_at": 1735689600,
    }
    msg = narada_body_to_rfc822(
        body,
        from_addr="alice@example.com",
        to_addrs=["bob@example.com"],
        cc_addrs=[],
    )
    back = rfc822_to_narada_body(msg)
    assert back["subject"] == "hello"
    assert back["body_text"].rstrip("\n") == "hi bob"
    assert alice_narada_id in back["sender"]
    assert bob_narada_id in back["to"]


def test_date_round_trip():
    body = {
        "subject": "t",
        "sender": "x",
        "to": ["y"],
        "body_text": "x",
        "sent_at": 1735689600,
    }
    msg = narada_body_to_rfc822(
        body, from_addr="a@x", to_addrs=["b@x"]
    )
    date = msg.get("Date")
    assert date
    parsed = email.utils.parsedate_to_datetime(str(date))
    assert int(parsed.timestamp()) == 1735689600


def test_invalid_sent_at_raises():
    body = {
        "subject": "t",
        "sender": "x",
        "to": ["y"],
        "body_text": "x",
        "sent_at": "not-a-number",
    }
    with pytest.raises(ConversionError):
        narada_body_to_rfc822(body, from_addr="a@x", to_addrs=["b@x"])


def test_rfc822_rejects_non_message():
    with pytest.raises(ConversionError):
        rfc822_to_narada_body("not a message")  # type: ignore[arg-type]


def test_multipart_text_plain_extracted():
    msg = EmailMessage()
    msg["Subject"] = "t"
    msg["From"] = "alice@example.com"
    msg["To"] = "bob@example.com"
    msg.set_content("hello world", subtype="plain", charset="utf-8")
    back = rfc822_to_naradata_body(msg) if False else rfc822_to_narada_body(msg)
    assert back["body_text"].rstrip("\n") == "hello world"
    assert back["subject"] == "t"
