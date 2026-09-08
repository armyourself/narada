"""IMAP inbound adapter for the gateway (Phase 5).

Wraps the existing Openmail ``IMAPManager`` so the gateway does
not duplicate connection logic. The adapter accepts an optional
``fetch`` callable for tests; the default delegates to
``node.src.modules.openmail.imap.IMAPManager.fetch``.
"""

from __future__ import annotations

from email.message import EmailMessage
from typing import Callable, Optional

from .errors import ImapFetchError, ImapMarkError


ImapFetch = Callable[[], list[EmailMessage]]


def default_fetch(
    *,
    imap_host: str,
    imap_port: int,
    username: str,
    password: str,
    folder: str = "INBOX",
    unseen_only: bool = True,
) -> tuple[ImapFetch, "ImapMarkFunc"]:
    """Build the default IMAP fetch + mark callable backed by
    ``IMAPManager``.

    Returns ``(fetch_fn, mark_fn)`` where *fetch_fn* returns a list
    of decoded ``EmailMessage`` objects and *mark_fn* marks UIDs as
    ``\\Seen`` on the remote server.
    """

    def _fetch() -> list[EmailMessage]:
        try:
            from node.src.modules.openmail.imap import IMAPManager  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise ImapFetchError(
                "IMAPManager import failed; the node runtime is required"
            ) from exc
        try:
            client = IMAPManager(username, password, host=imap_host, port=imap_port)
        except Exception as exc:
            raise ImapFetchError(f"imap connect failed: {exc}") from exc
        try:
            mailbox = client.get_emails(folder, unseen_only=unseen_only)
        except Exception as exc:
            raise ImapFetchError(f"imap fetch failed: {exc}") from exc
        out: list[EmailMessage] = []
        for record in getattr(mailbox, "emails", []) or []:
            raw = getattr(record, "raw", None)
            if raw:
                from email import message_from_bytes
                msg = message_from_bytes(raw)
            else:
                # Fall back to the parsed-fields view; the test
                # suite builds EmailMessage objects directly so
                # this branch rarely fires in practice.
                msg = EmailMessage()
                msg["Subject"] = str(getattr(record, "subject", "") or "")
                msg["From"] = str(getattr(record, "sender", "") or "")
                msg.set_content(
                    str(getattr(record, "body", "") or ""),
                    subtype="plain",
                    charset="utf-8",
                )
            # Stash the IMAP UID on the EmailMessage so callers can
            # mark it as seen after ingestion.
            uid = getattr(record, "uid", None)
            if uid is not None:
                msg["_narada_uid"] = str(uid)
            out.append(msg)
        return out

    def _mark_seen(uids: list[str], mark_folder: str = folder) -> None:
        """Mark the given UIDs as ``\\Seen`` on the remote IMAP server."""
        if not uids:
            return
        try:
            from node.src.modules.openmail.imap import IMAPManager  # type: ignore
            from node.src.modules.openmail.types import Mark  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise ImapFetchError(
                "IMAPManager import failed; the node runtime is required"
            ) from exc
        try:
            client = IMAPManager(username, password, host=imap_host, port=imap_port)
        except Exception as exc:
            raise ImapFetchError(f"imap connect failed: {exc}") from exc
        try:
            sequence_set = ",".join(uids)
            client.mark_email(sequence_set, Mark.Seen, folder=mark_folder)
        except Exception as exc:
            raise ImapMarkError(f"imap mark_seen failed: {exc}") from exc

    return _fetch, _mark_seen


ImapMarkFunc = Callable[[list[str]], None]


class ImapReceiver:
    """Inbound IMAP adapter for the gateway."""

    def __init__(
        self,
        *,
        fetch: Optional[ImapFetch] = None,
        mark_seen_fn: Optional[ImapMarkFunc] = None,
        imap_host: str = "",
        imap_port: int = 993,
        username: str = "",
        password: str = "",
        folder: str = "INBOX",
        unseen_only: bool = True,
    ) -> None:
        if fetch is None:
            self._fetch, self._mark_seen = default_fetch(
                imap_host=imap_host,
                imap_port=imap_port,
                username=username,
                password=password,
                folder=folder,
                unseen_only=unseen_only,
            )
        else:
            self._fetch = fetch
            self._mark_seen = mark_seen_fn or _noop_mark

    def fetch(self) -> list[EmailMessage]:
        return self._fetch()

    def mark_seen(self, uids: list[str]) -> None:
        """Mark the given IMAP UIDs as ``\\Seen`` on the remote server."""
        self._mark_seen(uids)


def _noop_mark(uids: list[str]) -> None:
    """No-op mark function used when no real IMAP connection is available."""
    pass


__all__ = ["ImapReceiver", "ImapFetch", "ImapMarkFunc", "default_fetch"]
