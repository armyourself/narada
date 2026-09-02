"""Narada protocol package (Phase 2 MVP).

The pieces:

* :mod:`.envelope` - sealed-and-signed message format (ChaCha20-Poly1305
  + Ed25519, sign-then-encrypt).
* :mod:`.transport` - ``NaradaTransport`` ABC + an HTTP-over-loopback
  implementation. Future work can add QUIC, libp2p, etc.
* :mod:`.directory` - ``NaradaDirectory`` ABC + a local JSON-backed
  contact list that maps ``narada1...`` public ids to base URLs.
* :mod:`.outbox` - persistent JSONL outbox with exponential-backoff
  retry for messages whose recipient is offline.
* :mod:`.inbox` - receiver-side helpers that verify, decrypt, and
  persist incoming envelopes to the local account store.
* :mod:`.adapter` - the Narada-protocol :class:`MailAdapter` that
  ties the above together. This is what the rest of the node calls.

A complete Narada message is built and consumed in roughly this shape::

    envelope = make_envelope(sender, recipient_public_id, body)
    transport.send(recipient_public_id, envelope.as_dict())
    # on the recipient:
    envelope = NaradaEnvelope.from_dict(request.json())
    body = open_envelope(envelope, recipient_identity)
    inbox.persist(body, sender_public_id=envelope.sender_public_id)
"""

from .adapter import NaradaAdapter
from .directory import NaradaDirectory, LocalContactList
from .envelope import (
    ENVELOPE_VERSION,
    NaradaBody,
    NaradaEnvelope,
    NaradaEnvelopeError,
    make_envelope,
    open_envelope,
)
from .inbox import NaradaInbox
from .outbox import Outbox, OutboxEntry
from .transport import (
    HttpNaradaTransport,
    NaradaTransport,
    NaradaTransportError,
)

__all__ = [
    "ENVELOPE_VERSION",
    "HttpNaradaTransport",
    "NaradaAdapter",
    "NaradaBody",
    "NaradaDirectory",
    "NaradaEnvelope",
    "NaradaEnvelopeError",
    "NaradaInbox",
    "NaradaTransport",
    "NaradaTransportError",
    "LocalContactList",
    "Outbox",
    "OutboxEntry",
    "make_envelope",
    "open_envelope",
]
