"""End-to-end tests for :mod:`gateway.gateway.orchestrator`."""

from __future__ import annotations

from email.message import EmailMessage

import pytest

from gateway.gateway.errors import NoMappingError, ConversionError
from gateway.gateway.mapping import IdentityMapping
from gateway.gateway.orchestrator import Gateway
from gateway.gateway.sender import SmtpSender


def _build_mapping(alice_narada_id, bob_narada_id):
    return IdentityMapping(
        narada_to_smtp={
            alice_narada_id: "alice@example.com",
            bob_narada_id: "bob@example.com",
        },
        smtp_to_narada={
            "alice@example.com": alice_narada_id,
            "bob@example.com": bob_narada_id,
        },
    )


def test_outbound_resolves_recipient_and_sends(
    sample_body, smtp_recorder, alice_narada_id, bob_narada_id
):
    mapping = _build_mapping(alice_narada_id, bob_narada_id)
    sender = SmtpSender(transport=smtp_recorder, smtp_from="gateway@example.com")
    gw = Gateway(mapping=mapping, sender=sender)
    ok, response = gw.deliver_outbound(
        narada_recipient_id=bob_narada_id,
        body=sample_body,
    )
    assert ok is True
    assert response == "250 OK"
    sent = smtp_recorder.sent
    assert len(sent) == 1
    msg = sent[0]
    assert msg["To"] == "bob@example.com"
    assert msg["Subject"] == "hello"
    assert msg.get_content().rstrip("\n") == "hi bob"


def test_outbound_unknown_recipient_refused(
    sample_body, smtp_recorder, alice_narada_id, bob_narada_id
):
    mapping = _build_mapping(alice_narada_id, bob_narada_id)
    sender = SmtpSender(transport=smtp_recorder)
    gw = Gateway(mapping=mapping, sender=sender)
    with pytest.raises(NoMappingError):
        gw.deliver_outbound(
            narada_recipient_id="narada1qstrangerxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            body=sample_body,
        )
    assert smtp_recorder.sent == []


def test_outbound_unknown_cc_refused(
    sample_body, smtp_recorder, alice_narada_id, bob_narada_id
):
    mapping = _build_mapping(alice_narada_id, bob_narada_id)
    sender = SmtpSender(transport=smtp_recorder)
    gw = Gateway(mapping=mapping, sender=sender)
    body = dict(sample_body)
    body["cc"] = ["narada1qstrangerxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"]
    with pytest.raises(NoMappingError):
        gw.deliver_outbound(narada_recipient_id=bob_narada_id, body=body)
    assert smtp_recorder.sent == []


def test_inbound_drops_anonymous_when_no_smtp_mapping(
    imap_recorder, alice_narada_id, bob_narada_id
):
    mapping = _build_mapping(alice_narada_id, bob_narada_id)
    sender = SmtpSender(transport=lambda msg: (True, "250 OK"))
    msg = EmailMessage()
    msg["From"] = "stranger@unknown.example"
    msg["To"] = "bob@example.com"
    msg["Subject"] = "hi"
    msg.set_content("hello", subtype="plain")
    imap_recorder.fetched.append(msg)
    gw = Gateway(
        mapping=mapping,
        sender=sender,
        receiver=type(
            "R",
            (),
            {"fetch": staticmethod(imap_recorder)},
        )(),
    )
    items = gw.poll_inbound()
    assert items == []


def test_inbound_resolves_known_sender(
    imap_recorder, alice_narada_id, bob_narada_id
):
    mapping = _build_mapping(alice_narada_id, bob_narada_id)
    sender = SmtpSender(transport=lambda msg: (True, "250 OK"))
    msg = EmailMessage()
    msg["From"] = "alice@example.com"
    msg["To"] = "bob@example.com"
    msg["Subject"] = "hi"
    msg.set_content("hello bob", subtype="plain")
    imap_recorder.fetched.append(msg)
    gw = Gateway(
        mapping=mapping,
        sender=sender,
        receiver=type(
            "R",
            (),
            {"fetch": staticmethod(imap_recorder)},
        )(),
    )
    items = gw.poll_inbound()
    assert len(items) == 1
    assert items[0].narada_recipient_id == bob_narada_id
    assert items[0].body["subject"] == "hi"


def test_inbound_without_receiver_raises(alice_narada_id, bob_narada_id):
    mapping = _build_mapping(alice_narada_id, bob_narada_id)
    sender = SmtpSender(transport=lambda msg: (True, "250 OK"))
    gw = Gateway(mapping=mapping, sender=sender)
    with pytest.raises(ConversionError):
        gw.poll_inbound()
