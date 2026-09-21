"""Nostr transport backend for Narada.

This package implements a Nostr-compatible transport that allows Narada
to send and receive messages through Nostr relays. It implements the
:class:`src.mail_abstraction.MailAdapter` interface so the rest of the
Narada node can use Nostr as a transport without knowing the details.

Supported NIPs:

* **NIP-01** — basic protocol flow, events, subscriptions, relay communication
* **NIP-04** — encrypted direct messages (using Schnorr-based encryption)
* **NIP-19** — bech32-encoded entities (npub, nsec, note)

Architecture::

    NaradaAdapter (legacy)     NostrAdapter (new)
           │                          │
           ▼                          ▼
    NaradaEnvelope              Nostr Event (NIP-01)
           │                          │
           ▼                          ▼
    NaradaTransport            NostrRelay (WebSocket)
           │                          │
           ▼                          ▼
    HTTP / QUIC                 Nostr Relays
"""

from .identity import NostrIdentity, generate_nostr_identity
from .events import NostrEvent, NostrFilter, create_event, verify_event
from .relay import NostrRelay, RelayPool
from .adapter import NostrAdapter
from .config import NostrConfig

__all__ = [
    "NostrConfig",
    "NostrEvent",
    "NostrFilter",
    "NostrAdapter",
    "NostrIdentity",
    "NostrRelay",
    "RelayPool",
    "create_event",
    "generate_nostr_identity",
    "verify_event",
]
