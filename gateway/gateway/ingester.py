"""Bulk IMAP -> Narada ingest (Phase 5).

:class:`ImapIngester` fetches messages from a remote IMAP mailbox and
converts each one into a Narada-sealed envelope that is persisted to
the local Narada inbox store.

The ingester is intentionally decoupled from the long-running daemon
— it can be invoked once for a bulk import or called repeatedly by
the daemon's polling loop.

Usage::

    ingester = ImapIngester(
        mapping=mapping,
        imap_host="imap.example.com",
        imap_port=993,
        username="alice@example.com",
        password="s3cret",
        identity=alice_identity,
        data_dir=Path("~/.openmail"),
    )
    result = ingester.ingest(limit=100)
    print(f"Imported {result.imported} messages, skipped {result.skipped}")
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .convert import rfc822_to_narada_body
from .errors import ConversionError, ImapFetchError, NoMappingError
from .mapping import IdentityMapping
from .receiver import ImapReceiver

log = logging.getLogger("narada.ingester")


@dataclass
class IngestResult:
    """Result of a bulk ingest operation."""

    imported: int = 0
    skipped: int = 0
    errors: int = 0
    uids_seen: list[str] = field(default_factory=list)


class ImapIngester:
    """Bulk ingest from IMAP into the Narada inbox store.

    Parameters
    ----------
    mapping:
        The identity mapping used to resolve sender/recipient addresses.
    identity:
        The Narada identity of the local user (for sealing envelopes).
    data_dir:
        The Narada node data directory.
    imap_host / imap_port / username / password / folder:
        IMAP connection parameters.
    fetch:
        Optional custom IMAP fetch callable (for tests).
    """

    def __init__(
        self,
        *,
        mapping: IdentityMapping,
        identity=None,
        data_dir: Path,
        imap_host: str = "",
        imap_port: int = 993,
        username: str = "",
        password: str = "",
        folder: str = "INBOX",
        fetch=None,
    ) -> None:
        self._mapping = mapping
        self._identity = identity
        self._data_dir = Path(data_dir)
        if fetch is not None:
            self._receiver = ImapReceiver(fetch=fetch)
        else:
            self._receiver = ImapReceiver(
                imap_host=imap_host,
                imap_port=imap_port,
                username=username,
                password=password,
                folder=folder,
                unseen_only=False,
            )

    def ingest(
        self,
        *,
        limit: Optional[int] = None,
        mark_seen: bool = True,
    ) -> IngestResult:
        """Fetch messages from IMAP and persist them to the Narada inbox.

        Parameters
        ----------
        limit:
            Maximum number of messages to ingest. *None* means all.
        mark_seen:
            If *True*, successfully imported messages are marked
            ``\\Seen`` on the remote IMAP server so they are not
            re-fetched on the next poll.

        Returns
        -------
        IngestResult
            Summary of the ingest operation.
        """
        result = IngestResult()
        try:
            rfc822_messages = self._receiver.fetch()
        except ImapFetchError as exc:
            log.error("IMAP fetch failed: %s", exc)
            result.errors = 1
            return result

        if limit is not None:
            rfc822_messages = rfc822_messages[:limit]

        imported_uids: list[str] = []
        for rfc822 in rfc822_messages:
            uid = rfc822.get("_narada_uid")
            imported_before = result.imported
            try:
                self._ingest_one(rfc822, result)
                if uid is not None and result.imported > imported_before:
                    imported_uids.append(uid)
            except Exception as exc:
                log.warning("Failed to ingest message: %s", exc)
                result.errors += 1

        if mark_seen and imported_uids:
            try:
                self._receiver.mark_seen(imported_uids)
            except Exception as exc:
                log.warning("Failed to mark messages as seen: %s", exc)

        return result

    def _ingest_one(self, rfc822, result: IngestResult) -> None:
        """Convert and persist a single RFC822 message."""
        from email.message import EmailMessage

        if not isinstance(rfc822, EmailMessage):
            raise ConversionError("expected EmailMessage instance")

        # Resolve the sender through the mapping.
        from_str = str(rfc822.get("From") or "")
        sender_id = self._resolve_sender(from_str)
        if sender_id is None:
            result.skipped += 1
            return

        # Resolve recipients.
        to_ids = self._resolve_recipients(rfc822, "To")
        cc_ids = self._resolve_recipients(rfc822, "Cc")
        all_recipient_ids = to_ids + cc_ids
        if not all_recipient_ids:
            result.skipped += 1
            return

        body = rfc822_to_narada_body(rfc822)
        # Override sender with the resolved Narada id.
        body["sender"] = sender_id

        # Write to the Narada mailbox JSONL.
        recipient_id = all_recipient_ids[0]
        self._write_to_mailbox(recipient_id, body, rfc822)
        result.imported += 1
        result.uids_seen.append(
            str(rfc822.get("Message-ID") or f"ingest-{result.imported}")
        )

    def _resolve_sender(self, from_str: str) -> Optional[str]:
        """Resolve a From header to a Narada public id."""
        if not from_str:
            return None
        # Check if it already contains a narada1... id.
        if "narada1" in from_str:
            return _extract_narada_id(from_str)
        # Look up in the mapping.
        email = _extract_email(from_str)
        try:
            return self._mapping.lookup_smtp_to_narada(email)
        except NoMappingError:
            return None

    def _resolve_recipients(self, msg, header: str) -> list[str]:
        """Resolve a header's addresses to Narada public ids."""
        raw = msg.get(header)
        if not raw:
            return []
        ids: list[str] = []
        for piece in str(raw).split(","):
            token = piece.strip()
            if not token:
                continue
            if "narada1" in token:
                nid = _extract_narada_id(token)
                if nid:
                    ids.append(nid)
                continue
            email = _extract_email(token)
            try:
                ids.append(self._mapping.lookup_smtp_to_narada(email))
            except NoMappingError:
                continue
        return ids

    def _write_to_mailbox(
        self, recipient_id: str, body: dict, rfc822
    ) -> None:
        """Append a Narada-body record to the mailbox JSONL file."""
        safe = _safe_account_id(recipient_id)
        mailbox_dir = self._data_dir / "etc"
        mailbox_dir.mkdir(parents=True, exist_ok=True)
        mailbox_path = mailbox_dir / f"mailbox.{safe}.jsonl"

        msg_id = str(rfc822.get("Message-ID") or f"ingest-{int(time.time())}")
        record = {
            "uid": msg_id,
            "source": "imap-ingest",
            "sender": body.get("sender", ""),
            "receivers": ", ".join(body.get("to", [])) if body.get("to") else recipient_id,
            "to": list(body.get("to", [])),
            "cc": list(body.get("cc", [])),
            "date": str(body.get("sent_at", int(time.time()))),
            "subject": body.get("subject", ""),
            "body": body.get("body_text", ""),
            "in_reply_to": "",
            "references": "",
            "list_unsubscribe": "",
            "list_unsubscribe_post": "",
            "flags": ["\\Seen"],
            "attachments": [],
            "message_id": f"<{msg_id}@Narada>",
            "received_at": int(time.time()),
        }
        line = json.dumps(record, separators=(",", ":"))
        with open(mailbox_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _safe_account_id(account_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._@+-" else "_" for c in account_id)
    return safe or "unknown"


def _extract_email(value: str) -> str:
    if "<" in value and ">" in value:
        inside = value.split("<", 1)[1].split(">", 1)[0]
        return inside.strip().lower()
    return value.strip().lower()


def _extract_narada_id(value: str) -> Optional[str]:
    token = value.strip()
    if token.startswith("narada1"):
        return token
    if "<" in token and ">" in token:
        inside = token.split("<", 1)[1].split(">", 1)[0]
        if inside.startswith("narada1"):
            return inside
    return None


__all__ = ["ImapIngester", "IngestResult"]
