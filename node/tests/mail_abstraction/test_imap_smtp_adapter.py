"""Tests for the Mail Abstraction layer.

Today these tests focus on the interface contract and the IMAP/SMTP
adapter's behaviour for the parts that *are* wired (connect, is_connected,
build_draft). The full message-sending/fetching paths are exercised
indirectly by the existing Openmail test suite; they will get adapter-level
coverage as the routers migrate to use the abstraction.
"""

from __future__ import annotations

import pytest

from src.mail_abstraction import (
    Address,
    Folder,
    IMAPSMTPAdapter,
    MailAdapterError,
    Message,
    MessageSource,
)
from src.narada import NaradaAdapter
from src.mail_abstraction.imap_smtp import convert_email, convert_folder
from src.modules.openmail.types import Email as OpenmailEmail, Folder as OpenmailFolder


def test_message_source_distinguishes_imap_from_narada():
    assert MessageSource.IMAP.value == "imap"
    assert MessageSource.Narada.value == "Narada"


def test_address_str_with_name():
    a = Address(address="alice@example.com", name="Alice")
    assert str(a) == "Alice <alice@example.com>"


def test_address_str_without_name():
    a = Address(address="alice@example.com")
    assert str(a) == "alice@example.com"


def test_imap_smtp_adapter_is_connected_false_initially():
    adapter = IMAPSMTPAdapter()
    assert adapter.is_connected() is False
    assert adapter.source is MessageSource.IMAP


def test_narada_adapter_is_connected_true_by_default():
    # NaradaAdapter is connectionless; the new implementation reports
    # is_connected() as True once it has loaded (or attempted to
    # load) its local identity.
    from src.narada_identity.keystore import InMemoryKeystore as _IKS
    from src.narada_identity.identity import generate_identity as _gen
    ks = _IKS()
    _gen("bob@example.com", keystore=ks)
    adapter = NaradaAdapter("bob@example.com", keystore=ks)
    assert adapter.is_connected() is True
    assert adapter.source is MessageSource.Narada


def test_narada_adapter_connect_succeeds_when_identity_loaded():
    from src.narada_identity.keystore import InMemoryKeystore as _IKS
    from src.narada_identity.identity import generate_identity as _gen
    ks = _IKS()
    _gen("bob@example.com", keystore=ks)
    adapter = NaradaAdapter("bob@example.com", keystore=ks)
    ok, msg = adapter.connect()
    assert ok is True
    assert "ready" in msg.lower()


def test_narada_adapter_connect_fails_without_identity():
    from src.narada_identity.keystore import InMemoryKeystore as _IKS
    ks = _IKS()
    adapter = NaradaAdapter("nobody@example.com", keystore=ks)
    ok, msg = adapter.connect()
    assert ok is False
    assert "identity" in msg.lower()


def test_imap_smtp_adapter_transport_methods_raise_until_migrated():
    adapter = IMAPSMTPAdapter()
    with pytest.raises(MailAdapterError):
        adapter.list_folders()
    with pytest.raises(MailAdapterError):
        adapter.fetch_messages("INBOX")
    with pytest.raises(MailAdapterError):
        adapter.send_message(
            from_address=Address(address="a@example.com"),
            to_addresses=[Address(address="b@example.com")],
            subject="x",
            body="y",
        )
    with pytest.raises(MailAdapterError):
        adapter.watch("INBOX", lambda m: None)


def test_imap_smtp_adapter_disconnect_when_not_connected():
    adapter = IMAPSMTPAdapter()
    # Disconnect should be callable on the IMAP adapter even when not
    # connected; the NaradaAdapter's disconnect is a no-op in the
    # same situation.
    from src.narada_identity.keystore import InMemoryKeystore as _IKS
    from src.narada_identity.identity import generate_identity as _gen
    ks = _IKS()
    _gen("bob@example.com", keystore=ks)
    Narada = NaradaAdapter("bob@example.com", keystore=ks)
    ok, _ = Narada.disconnect()
    assert ok is True


def test_build_draft_converts_addresses():
    adapter = IMAPSMTPAdapter()
    draft = adapter.build_draft(
        from_address=Address(address="alice@example.com", name="Alice"),
        to_addresses=[
            Address(address="bob@example.com", name="Bob"),
            Address(address="carol@example.com"),
        ],
        subject="Hello",
        body="Body",
        cc=[Address(address="dave@example.com")],
    )
    assert draft.sender == "Alice <alice@example.com>"
    assert "Bob <bob@example.com>" in draft.receivers
    assert "carol@example.com" in draft.receivers
    assert "dave@example.com" in draft.cc
    assert draft.subject == "Hello"


def test_convert_email_projects_fields():
    raw = OpenmailEmail(
        message_id="<abc@example.com>",
        uid="42",
        sender="Alice <alice@example.com>",
        receivers="Bob <bob@example.com>, carol@example.com",
        date="2024-01-01",
        subject="hi",
        body="hello",
        flags=["\\Seen", "\\Flagged"],
    )
    msg = convert_email(raw, folder="INBOX")
    assert isinstance(msg, Message)
    assert msg.uid == "42"
    assert msg.folder == "INBOX"
    assert msg.source is MessageSource.IMAP
    assert msg.subject == "hi"
    assert msg.from_address.address == "alice@example.com"
    assert msg.from_address.name == "Alice"
    addrs = [a.address for a in msg.to_addresses]
    assert "bob@example.com" in addrs
    assert "carol@example.com" in addrs
    assert msg.is_read is True
    assert msg.is_flagged is True


def test_convert_folder_handles_enum_and_string():
    f1 = convert_folder(OpenmailFolder.Inbox)
    assert isinstance(f1, Folder)
    assert f1.name == "Inbox"
    f2 = convert_folder("Custom/Folder")
    assert f2.name == "Custom/Folder"
