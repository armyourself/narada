"""Tests for :mod:`gateway.gateway.ingester`."""

from __future__ import annotations

import json
from email.message import EmailMessage
from pathlib import Path

import pytest

from gateway.gateway.errors import NoMappingError
from gateway.gateway.ingester import ImapIngester, IngestResult
from gateway.gateway.mapping import IdentityMapping


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


class TestImapIngester:
    def test_ingest_single_message(
        self, tmp_path: Path, alice_narada_id, bob_narada_id
    ):
        mapping = _build_mapping(alice_narada_id, bob_narada_id)

        msg = EmailMessage()
        msg["From"] = "alice@example.com"
        msg["To"] = "bob@example.com"
        msg["Subject"] = "Hello"
        msg.set_content("Hi Bob", subtype="plain")

        def _fetch():
            return [msg]

        ingester = ImapIngester(
            mapping=mapping,
            data_dir=tmp_path,
            fetch=_fetch,
        )
        result = ingester.ingest(mark_seen=False)
        assert result.imported == 1
        assert result.skipped == 0
        assert result.errors == 0

        # Verify the mailbox file was created.
        mailbox_files = list((tmp_path / "etc").glob("mailbox.*.jsonl"))
        assert len(mailbox_files) == 1
        records = [
            json.loads(line)
            for line in mailbox_files[0].read_text().splitlines()
            if line.strip()
        ]
        assert len(records) == 1
        assert records[0]["subject"] == "Hello"
        assert records[0]["source"] == "imap-ingest"

    def test_ingest_skips_unknown_sender(
        self, tmp_path: Path, alice_narada_id, bob_narada_id
    ):
        mapping = _build_mapping(alice_narada_id, bob_narada_id)

        msg = EmailMessage()
        msg["From"] = "stranger@unknown.example"
        msg["To"] = "bob@example.com"
        msg["Subject"] = "spam"
        msg.set_content("ignore me", subtype="plain")

        def _fetch():
            return [msg]

        ingester = ImapIngester(
            mapping=mapping,
            data_dir=tmp_path,
            fetch=_fetch,
        )
        result = ingester.ingest(mark_seen=False)
        assert result.imported == 0
        assert result.skipped == 1

    def test_ingest_skips_no_recipient(
        self, tmp_path: Path, alice_narada_id, bob_narada_id
    ):
        mapping = _build_mapping(alice_narada_id, bob_narada_id)

        msg = EmailMessage()
        msg["From"] = "alice@example.com"
        msg["To"] = "stranger@unknown.example"
        msg["Subject"] = "Test"
        msg.set_content("no recipient", subtype="plain")

        def _fetch():
            return [msg]

        ingester = ImapIngester(
            mapping=mapping,
            data_dir=tmp_path,
            fetch=_fetch,
        )
        result = ingester.ingest(mark_seen=False)
        assert result.imported == 0
        assert result.skipped == 1

    def test_ingest_respects_limit(
        self, tmp_path: Path, alice_narada_id, bob_narada_id
    ):
        mapping = _build_mapping(alice_narada_id, bob_narada_id)

        msgs = []
        for i in range(5):
            msg = EmailMessage()
            msg["From"] = "alice@example.com"
            msg["To"] = "bob@example.com"
            msg["Subject"] = f"Msg {i}"
            msg.set_content(f"Body {i}", subtype="plain")
            msgs.append(msg)

        def _fetch():
            return msgs

        ingester = ImapIngester(
            mapping=mapping,
            data_dir=tmp_path,
            fetch=_fetch,
        )
        result = ingester.ingest(limit=2, mark_seen=False)
        assert result.imported == 2

    def test_ingest_with_narada_sender(
        self, tmp_path: Path, alice_narada_id, bob_narada_id
    ):
        mapping = _build_mapping(alice_narada_id, bob_narada_id)

        msg = EmailMessage()
        msg["From"] = f"Name <{alice_narada_id}@gateway>"
        msg["To"] = "bob@example.com"
        msg["Subject"] = "From Narada"
        msg.set_content("hello", subtype="plain")

        def _fetch():
            return [msg]

        ingester = ImapIngester(
            mapping=mapping,
            data_dir=tmp_path,
            fetch=_fetch,
        )
        result = ingester.ingest(mark_seen=False)
        assert result.imported == 1

    def test_ingest_marks_seen_after_import(
        self, tmp_path: Path, alice_narada_id, bob_narada_id
    ):
        """Verify that successfully imported UIDs are marked as \\Seen."""
        mapping = _build_mapping(alice_narada_id, bob_narada_id)
        marked_uids: list[str] = []

        msg1 = EmailMessage()
        msg1["From"] = "alice@example.com"
        msg1["To"] = "bob@example.com"
        msg1["Subject"] = "First"
        msg1.set_content("body1", subtype="plain")
        msg1["_narada_uid"] = "101"

        msg2 = EmailMessage()
        msg2["From"] = "alice@example.com"
        msg2["To"] = "bob@example.com"
        msg2["Subject"] = "Second"
        msg2.set_content("body2", subtype="plain")
        msg2["_narada_uid"] = "102"

        def _fetch():
            return [msg1, msg2]

        def _mark_seen(uids: list[str]):
            marked_uids.extend(uids)

        ingester = ImapIngester(
            mapping=mapping,
            data_dir=tmp_path,
            fetch=_fetch,
        )
        # Inject the mark_seen function directly.
        ingester._receiver._mark_seen = _mark_seen

        result = ingester.ingest(mark_seen=True)
        assert result.imported == 2
        assert marked_uids == ["101", "102"]

    def test_ingest_does_not_mark_seen_when_disabled(
        self, tmp_path: Path, alice_narada_id, bob_narada_id
    ):
        """Verify that mark_seen=False skips the IMAP flag operation."""
        mapping = _build_mapping(alice_narada_id, bob_narada_id)
        marked_uids: list[str] = []

        msg = EmailMessage()
        msg["From"] = "alice@example.com"
        msg["To"] = "bob@example.com"
        msg["Subject"] = "Test"
        msg.set_content("body", subtype="plain")
        msg["_narada_uid"] = "201"

        def _fetch():
            return [msg]

        def _mark_seen(uids: list[str]):
            marked_uids.extend(uids)

        ingester = ImapIngester(
            mapping=mapping,
            data_dir=tmp_path,
            fetch=_fetch,
        )
        ingester._receiver._mark_seen = _mark_seen

        result = ingester.ingest(mark_seen=False)
        assert result.imported == 1
        assert marked_uids == []

    def test_ingest_only_marks_imported_not_skipped(
        self, tmp_path: Path, alice_narada_id, bob_narada_id
    ):
        """Only UIDs of successfully imported messages are marked."""
        mapping = _build_mapping(alice_narada_id, bob_narada_id)
        marked_uids: list[str] = []

        msg_good = EmailMessage()
        msg_good["From"] = "alice@example.com"
        msg_good["To"] = "bob@example.com"
        msg_good["Subject"] = "Good"
        msg_good.set_content("ok", subtype="plain")
        msg_good["_narada_uid"] = "301"

        msg_bad = EmailMessage()
        msg_bad["From"] = "stranger@unknown.example"
        msg_bad["To"] = "bob@example.com"
        msg_bad["Subject"] = "Bad"
        msg_bad.set_content("skip", subtype="plain")
        msg_bad["_narada_uid"] = "302"

        def _fetch():
            return [msg_good, msg_bad]

        def _mark_seen(uids: list[str]):
            marked_uids.extend(uids)

        ingester = ImapIngester(
            mapping=mapping,
            data_dir=tmp_path,
            fetch=_fetch,
        )
        ingester._receiver._mark_seen = _mark_seen

        result = ingester.ingest(mark_seen=True)
        assert result.imported == 1
        assert result.skipped == 1
        assert marked_uids == ["301"]
