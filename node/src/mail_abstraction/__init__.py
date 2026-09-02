"""Mail Abstraction layer for the Narada node.

This package defines a single ``MailAdapter`` interface that the Narada
node uses to talk to mail sources, regardless of transport.

* :class:`IMAPSMTPAdapter` - wraps the existing Openmail IMAP/SMTP code.
  Today, every router and the WebSocket notifications flow goes
  through this path directly. The adapter is the well-typed seam
  that the routers can be migrated to in a follow-up without
  changing behaviour.
* :class:`src.narada.adapter.NaradaAdapter` - the Narada protocol
  transport. Lives in the ``Narada`` package now (Phase 2+).
"""

from .base import (
    Address,
    Folder,
    MailAdapter,
    MailAdapterError,
    Message,
    MessageSource,
)
from .imap_smtp import IMAPSMTPAdapter

__all__ = [
    "Address",
    "Folder",
    "IMAPSMTPAdapter",
    "MailAdapter",
    "MailAdapterError",
    "Message",
    "MessageSource",
]
