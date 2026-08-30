"""Mail Abstraction layer for the Lattice node.

This package defines a single ``MailAdapter`` interface that the Lattice node
uses to talk to mail sources, regardless of transport. Two adapters live
underneath it:

* :class:`IMAPSMTPAdapter` - wraps the existing Openmail IMAP/SMTP code.
  Today, every router and the WebSocket notifications flow goes through
  this path directly. The adapter is the well-typed seam that the routers
  can be migrated to in a follow-up without changing behaviour.
* :class:`LatticeAdapter` - stub for the future Lattice protocol transport
  (Phase 2+ of the Lattice roadmap). All transport methods currently raise
  ``NotImplementedError`` with a clear message.
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
from .lattice import LatticeAdapter

__all__ = [
    "Address",
    "Folder",
    "IMAPSMTPAdapter",
    "LatticeAdapter",
    "MailAdapter",
    "MailAdapterError",
    "Message",
    "MessageSource",
]
