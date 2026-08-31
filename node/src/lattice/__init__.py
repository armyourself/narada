"""Lattice protocol package (Phase 2 MVP).

The pieces:

* :mod:`.envelope` - sealed-and-signed message format (ChaCha20-Poly1305
  + Ed25519, sign-then-encrypt).
* :mod:`.transport` - ``LatticeTransport`` ABC + an HTTP-over-loopback
  implementation. Future work can add QUIC, libp2p, etc.
* :mod:`.directory` - ``LatticeDirectory`` ABC + a local JSON-backed
  contact list that maps ``lattice1...`` public ids to base URLs.
* :mod:`.outbox` - persistent JSONL outbox with exponential-backoff
  retry for messages whose recipient is offline.
* :mod:`.inbox` - receiver-side helpers that verify, decrypt, and
  persist incoming envelopes to the local account store.
* :mod:`.adapter` - the Lattice-protocol :class:`MailAdapter` that
  ties the above together. This is what the rest of the node calls.

A complete Lattice message is built and consumed in roughly this shape::

    envelope = make_envelope(sender, recipient_public_id, body)
    transport.send(recipient_public_id, envelope.as_dict())
    # on the recipient:
    envelope = LatticeEnvelope.from_dict(request.json())
    body = open_envelope(envelope, recipient_identity)
    inbox.persist(body, sender_public_id=envelope.sender_public_id)
"""

from .adapter import LatticeAdapter
from .directory import LatticeDirectory, LocalContactList
from .envelope import (
    ENVELOPE_VERSION,
    LatticeBody,
    LatticeEnvelope,
    LatticeEnvelopeError,
    make_envelope,
    open_envelope,
)
from .inbox import LatticeInbox
from .outbox import Outbox, OutboxEntry
from .transport import (
    HttpLatticeTransport,
    LatticeTransport,
    LatticeTransportError,
)

__all__ = [
    "ENVELOPE_VERSION",
    "HttpLatticeTransport",
    "LatticeAdapter",
    "LatticeBody",
    "LatticeDirectory",
    "LatticeEnvelope",
    "LatticeEnvelopeError",
    "LatticeInbox",
    "LatticeTransport",
    "LatticeTransportError",
    "LocalContactList",
    "Outbox",
    "OutboxEntry",
    "make_envelope",
    "open_envelope",
]
