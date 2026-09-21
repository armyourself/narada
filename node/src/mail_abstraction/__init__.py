"""Mail Abstraction layer.

This package defines a single ``MailAdapter`` interface that the application
uses to talk to mail sources, regardless of transport.

* :class:`IMAPSMTPAdapter` - wraps the existing Openmail IMAP/SMTP code.
* :class:`src.nostr.adapter.NostrAdapter` - Nostr transport via relays.
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
