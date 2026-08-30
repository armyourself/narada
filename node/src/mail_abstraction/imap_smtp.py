"""IMAP/SMTP adapter that wraps the existing Openmail client.

This adapter is the production adapter for the Lattice node today: every
account that has been added through the existing ``/add-account`` endpoint
talks IMAP and SMTP through the ``Openmail`` class in
``src.modules.openmail``.

The :class:`IMAPSMTPAdapter` exposes the narrow :class:`MailAdapter`
interface used by future code, while still holding a reference to the
underlying :class:`Openmail` instance for callers (like today's routers)
that need the full IMAP/SMTP surface. The migration path is therefore:

1. Adapters (this file) are tested in isolation.
2. Routers are migrated to use the adapter methods that fit their needs
   in follow-up PRs. The :attr:`client` accessor keeps that migration
   incremental.

Note on the underlying API:

The Openmail IMAP/SMTP surface is rich and idiomatic for those protocols
(e.g. ``IMAPManager.get_emails`` requires a prior ``search_emails`` call
and operates on a search result, not a folder; ``SMTPManager.send_email``
takes a :class:`Draft` object rather than loose parameters). The methods
on this adapter are intentionally narrow: the :class:`MailAdapter`
interface is the contract the rest of the Lattice node should rely on,
not a 1:1 mirror of the IMAP/SMTP API. As routers migrate, more
translation will live in helper functions next to the adapter.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from src.modules.openmail import Openmail
from src.modules.openmail.imap import IMAPManagerException
from src.modules.openmail.smtp import SMTPManagerException
from src.modules.openmail.types import (
    Attachment as OpenmailAttachment,
    Draft as OpenmailDraft,
    Email as OpenmailEmail,
    Folder as OpenmailFolder,
)
from src.modules.openmail.utils import extract_email_address

from .base import (
    Address,
    Folder,
    MailAdapter,
    MailAdapterError,
    Message,
    MessageSource,
)


def _has_flag(flags: Optional[list[str]], needle: str) -> bool:
    if not flags:
        return False
    return any(needle in f for f in flags)


class IMAPSMTPAdapter(MailAdapter):
    """Adapts the Openmail IMAP+SMTP client to the Lattice MailAdapter interface."""

    source = MessageSource.IMAP

    def __init__(self, client: Optional[Openmail] = None) -> None:
        self._client = client or Openmail()
        self._lock = threading.Lock()

    @property
    def client(self) -> Openmail:
        """Underlying Openmail client.

        Preserved for the existing routers that need the full IMAP/SMTP
        surface. New code should prefer the :class:`MailAdapter` methods.
        """
        return self._client

    def connect(
        self,
        email_address: str,
        password: str,
        /,
        *,
        imap_host: str = "",
        imap_port: int = 993,
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_local_hostname: Optional[str] = None,
        timeout: int = 30,
    ) -> tuple[bool, str]:
        try:
            return self._client.connect(
                email_address,
                password,
                imap_host=imap_host,
                imap_port=imap_port,
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                smtp_local_hostname=smtp_local_hostname,
                timeout=timeout,
            )
        except (IMAPManagerException, SMTPManagerException) as exc:
            raise MailAdapterError(str(exc)) from exc

    def disconnect(self) -> tuple[bool, str]:
        try:
            return self._client.disconnect()
        except (IMAPManagerException, SMTPManagerException) as exc:
            raise MailAdapterError(str(exc)) from exc

    def is_connected(self) -> bool:
        with self._lock:
            try:
                return bool(self._client._imap and self._client._smtp)
            except Exception:
                return False

    def list_folders(self) -> list[Folder]:
        raise MailAdapterError(
            "IMAPSMTPAdapter.list_folders is not yet wired; the routers "
            "currently call IMAPManager.get_folders directly. This will be "
            "migrated in the router-cleanup PR."
        )

    def fetch_messages(
        self,
        folder: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Message]:
        raise MailAdapterError(
            "IMAPSMTPAdapter.fetch_messages is not yet wired; IMAPManager "
            "requires a prior search_emails call. Use the Openmail client "
            "directly until the router migration lands."
        )

    def send_message(
        self,
        *,
        from_address: Address,
        to_addresses: list[Address],
        subject: str,
        body: str,
        cc: Optional[list[Address]] = None,
        bcc: Optional[list[Address]] = None,
        attachments: Optional[list[tuple[str, bytes]]] = None,
        is_html: bool = False,
    ) -> tuple[bool, str]:
        raise MailAdapterError(
            "IMAPSMTPAdapter.send_message is not yet wired; use "
            "SMTPManager.send_email(Draft) directly until the router "
            "migration lands."
        )

    def build_draft(
        self,
        *,
        from_address: Address,
        to_addresses: list[Address],
        subject: str,
        body: str,
        cc: Optional[list[Address]] = None,
        bcc: Optional[list[Address]] = None,
        attachments: Optional[list[tuple[str, bytes]]] = None,
    ) -> OpenmailDraft:
        """Build an Openmail :class:`Draft` from adapter-style parameters.

        Useful for callers that want to keep the adapter contract in their
        signature but still hand the Draft to ``SMTPManager.send_email``.
        """
        sender_str = str(from_address)
        receivers = [str(a) for a in to_addresses]
        cc_str = ", ".join(str(a) for a in (cc or []))
        bcc_str = ", ".join(str(a) for a in (bcc or []))
        attachment_dicts = [
            {"name": name, "data": data} for name, data in (attachments or [])
        ]
        return OpenmailDraft(
            sender=sender_str,
            receivers=receivers,
            cc=cc_str,
            bcc=bcc_str,
            subject=subject,
            body=body,
            attachments=attachment_dicts,
        )

    def watch(self, folder: str, on_new_message: Callable[[Message], None]) -> None:
        """IMAP supports push via IDLE; the underlying client exposes it as
        ``any_new_email`` / ``get_recent_emails``. The adapter here only
        signals capability; the existing WebSocket flow continues to use the
        Openmail client directly until the routers migrate.
        """
        raise MailAdapterError(
            "IMAPSMTPAdapter.watch is not implemented; use the Openmail "
            "client's IDLE flow directly until the router migration lands."
        )


def convert_email(raw: OpenmailEmail, folder: str) -> Message:
    """Project an Openmail :class:`Email` onto the adapter's :class:`Message`.

    Exposed at module level so future router migrations can reuse the
    conversion without holding an adapter instance.
    """
    return Message(
        uid=str(raw.uid or ""),
        folder=folder,
        source=MessageSource.IMAP,
        subject=raw.subject or "",
        from_address=_address_from_string(raw.sender or ""),
        to_addresses=[_address_from_string(a) for a in (raw.receivers or "").split(",") if a.strip()],
        date=raw.date or "",
        preview=None,
        has_attachments=bool(raw.attachments),
        is_read=_has_flag(raw.flags, "\\Seen"),
        is_flagged=_has_flag(raw.flags, "\\Flagged"),
        raw=None,
    )


def convert_folder(raw: OpenmailFolder | str) -> Folder:
    """Project an Openmail :class:`Folder` onto the adapter's :class:`Folder`."""
    if isinstance(raw, OpenmailFolder):
        return Folder(
            name=str(raw.value),
            delimiter="/",
            is_selectable=True,
            children=[],
        )
    return Folder(name=str(raw), delimiter="/", is_selectable=True, children=[])


def _address_from_string(value: str) -> Address:
    text = (value or "").strip()
    if not text:
        return Address(address="")
    if "<" in text and ">" in text:
        name_part, _, addr_part = text.partition("<")
        name = name_part.strip().strip('"') or None
        addr = (addr_part.split(">", 1)[0] or "").strip()
        return Address(address=addr, name=name)
    extracted = extract_email_address(text) or text
    return Address(address=extracted)


__all__ = ["IMAPSMTPAdapter", "convert_email", "convert_folder"]
