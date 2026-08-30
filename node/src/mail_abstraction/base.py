"""Base interface for Lattice mail adapters.

A :class:`MailAdapter` is the single object a Lattice node uses to talk to a
mail source. Today the only production adapter is
:class:`src.mail_abstraction.imap_smtp.IMAPSMTPAdapter`; future adapters will
speak the Lattice protocol or, eventually, other transports.

The interface is intentionally narrow: enough to send, fetch, list folders,
and watch for new messages. The existing Openmail IMAP/SMTP surface is
significantly wider; the wrapper in :mod:`src.mail_abstraction.imap_smtp`
exposes both views so the existing routers keep working unchanged.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MailAdapterError(Exception):
    """Base class for adapter-level errors."""


class MessageSource(str, Enum):
    """Where a message came from.

    Used by the Lattice client UI to show a small indicator distinguishing
    messages delivered over conventional email (IMAP) from those delivered
    over the Lattice protocol. Today only ``IMAP`` is produced; ``LATTICE``
    will appear in Phase 2+.
    """

    IMAP = "imap"
    LATTICE = "lattice"


@dataclass(frozen=True)
class Address:
    """A single email address, optionally with a display name."""

    address: str
    name: Optional[str] = None

    def __str__(self) -> str:
        if self.name:
            return f"{self.name} <{self.address}>"
        return self.address


@dataclass
class Message:
    """A minimal cross-adapter message view.

    Adapters may carry more information; this is the projection the rest of
    the Lattice node should rely on. ``raw`` is the adapter-specific blob
    (e.g. RFC822 bytes for IMAP) for callers that need it.
    """

    uid: str
    folder: str
    source: MessageSource
    subject: str
    from_address: Address
    to_addresses: list[Address] = field(default_factory=list)
    date: Optional[str] = None
    preview: Optional[str] = None
    has_attachments: bool = False
    is_read: bool = False
    is_flagged: bool = False
    raw: Optional[bytes] = None


@dataclass
class Folder:
    name: str
    delimiter: str = "/"
    is_selectable: bool = True
    children: list[str] = field(default_factory=list)


class MailAdapter(ABC):
    """Abstract mail adapter.

    Concrete adapters implement :meth:`connect`, :meth:`disconnect`,
    :meth:`list_folders`, :meth:`fetch_messages`, :meth:`send_message`,
    and :meth:`watch`. The :meth:`is_connected` predicate is provided.
    """

    source: MessageSource

    @abstractmethod
    def connect(self) -> tuple[bool, str]:
        """Open the underlying connection(s). Returns ``(success, message)``."""

    @abstractmethod
    def disconnect(self) -> tuple[bool, str]:
        """Close the underlying connection(s). Returns ``(success, message)``."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the adapter is currently usable."""

    @abstractmethod
    def list_folders(self) -> list[Folder]:
        """Enumerate the available folders/mailboxes."""

    @abstractmethod
    def fetch_messages(
        self,
        folder: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Message]:
        """Fetch a page of messages from ``folder``."""

    @abstractmethod
    def send_message(
        self,
        *,
        from_address: Address,
        to_addresses: list[Address],
        subject: str,
        body: str,
        cc: list[Address] | None = None,
        bcc: list[Address] | None = None,
        attachments: list[tuple[str, bytes]] | None = None,
        is_html: bool = False,
    ) -> tuple[bool, str]:
        """Send a message. Returns ``(success, message)``."""

    @abstractmethod
    def watch(
        self,
        folder: str,
        on_new_message,
    ) -> None:
        """Register a callback for new messages in ``folder``.

        Adapters that do not support push (e.g. a stub) may poll on a
        sensible interval. ``on_new_message`` receives a :class:`Message`.
        """


__all__ = [
    "Address",
    "Folder",
    "MailAdapter",
    "MailAdapterError",
    "Message",
    "MessageSource",
]
