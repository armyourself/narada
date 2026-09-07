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

The Phase 5 deliverable ships these pieces and exercises them in
tests; live SMTP/IMAP connectivity is held until the audit in
Phase 6.
"""

from .convert import narada_body_to_rfc822, rfc822_to_narada_body
from .errors import (
    ConversionError,
    GatewayError,
    ImapFetchError,
    NoMappingError,
    SmtpSendError,
)
from .mapping import IdentityMapping
from .orchestrator import Gateway, InboundItem
from .receiver import ImapFetch, ImapReceiver, default_fetch
from .sender import SmtpSender, SmtpTransport, default_transport


__all__ = [
    "ConversionError",
    "Gateway",
    "GatewayError",
    "IdentityMapping",
    "ImapFetch",
    "ImapFetchError",
    "ImapReceiver",
    "InboundItem",
    "NoMappingError",
    "SmtpSendError",
    "SmtpSender",
    "SmtpTransport",
    "default_fetch",
    "default_transport",
    "narada_body_to_rfc822",
    "rfc822_to_narada_body",
]
