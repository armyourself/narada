"""Narada Gateway package (Phase 5).

The gateway is the trust boundary between the Narada protocol and
conventional email infrastructure (SMTP / IMAP). It exposes a
narrow surface:

* :class:`IdentityMapping` -- the Narada <-> conventional-address
  table, loaded from JSON.
* :func:`narada_body_to_rfc822` / :func:`rfc822_to_narada_body` --
  the body conversion contract.
* :class:`SmtpSender` -- the outbound SMTP adapter.
* :class:`ImapReceiver` -- the inbound IMAP adapter.
* :class:`Gateway` -- the orchestrator that wires the above
  together for both directions.
* :class:`NaradaImapServer` -- read-only IMAP server exposing
  the Narada mailbox to legacy clients.
* :class:`ImapIngester` -- bulk import from IMAP into Narada.
* :class:`GatewayDaemon` -- long-running daemon with polling.
"""

from .convert import narada_body_to_rfc822, rfc822_to_narada_body
from .daemon import GatewayDaemon
from .daemon_control import ControlServer
from .errors import (
    ConversionError,
    GatewayError,
    ImapFetchError,
    ImapMarkError,
    NoMappingError,
    SmtpSendError,
)
from .imap_server import NaradaImapServer
from .ingester import ImapIngester, IngestResult
from .mapping import IdentityMapping
from .orchestrator import Gateway, InboundItem
from .receiver import ImapFetch, ImapReceiver, default_fetch
from .sender import SmtpSender, SmtpTransport, default_transport


__all__ = [
    "ConversionError",
    "ControlServer",
    "Gateway",
    "GatewayDaemon",
    "GatewayError",
    "IdentityMapping",
    "ImapFetch",
    "ImapFetchError",
    "ImapIngester",
    "ImapMarkError",
    "ImapReceiver",
    "InboundItem",
    "IngestResult",
    "NaradaImapServer",
    "NoMappingError",
    "SmtpSendError",
    "SmtpSender",
    "SmtpTransport",
    "default_fetch",
    "default_transport",
    "narada_body_to_rfc822",
    "rfc822_to_narada_body",
]
