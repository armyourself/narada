"""IMAP inbound adapter for the gateway (Phase 5).

Wraps the existing Openmail ``IMAPManager`` so the gateway does
not duplicate connection logic. The adapter accepts an optional
``fetch`` callable for tests; the default delegates to
``node.src.modules.openmail.imap.IMAPManager.fetch``.
"""

from __future__ import annotations

from email.message import EmailMessage
from typing import Callable, Optional

from .errors import ImapFetchError


ImapFetch = Callable[[], list[EmailMessage]]


def default_fetch(
    *,
    imap_host: str,
    imap_port: int,
    username: str,
    password: str,
    folder: str = "INBOX",
    unseen_only: bool = True,
) -> ImapFetch:
    """Build the default IMAP fetch callable backed by
    ``IMAPManager``.

    The closure returns a list of decoded ``EmailMessage`` objects
    on each call. The caller is responsible for marking them
    ``\\Seen`` after successful ingestion.
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
            out.append(msg)
        return out

    return _fetch


class ImapReceiver:
    """Inbound IMAP adapter for the gateway."""

    def __init__(
        self,
        *,
        fetch: Optional[ImapFetch] = None,
        imap_host: str = "",
        imap_port: int = 993,
        username: str = "",
        password: str = "",
        folder: str = "INBOX",
        unseen_only: bool = True,
    ) -> None:
        if fetch is None:
            self._fetch = default_fetch(
                imap_host=imap_host,
                imap_port=imap_port,
                username=username,
                password=password,
                folder=folder,
                unseen_only=unseen_only,
            )
        else:
            self._fetch = fetch

    def fetch(self) -> list[EmailMessage]:
        return self._fetch()


__all__ = ["ImapReceiver", "ImapFetch", "default_fetch"]
