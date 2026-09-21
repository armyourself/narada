"""NIP-01 event creation, signing, and verification.

NIP-01 defines the basic Nostr event format:

    {
      "id": <32-byte SHA-256 hash of serialized event>,
      "pubkey": <32-byte hex public key>,
      "created_at": <unix timestamp>,
      "kind": <event kind number>,
      "tags": [[...], ...],
      "content": <string>,
      "sig": <64-byte hex signature>
    }

The event id is computed over the serialized array:
    [0, pubkey, created_at, kind, tags, content]

The signature is an Ed25519 signature over the event id hex string.

This module implements:

* :class:`NostrEvent` — the event data structure
* :class:`NostrFilter` — subscription filter (NIP-01)
* :func:`create_event` — create and sign an event
* :func:`verify_event` — verify an event's id and signature
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from .identity import NostrIdentity


# --- Event kinds ------------------------------------------------------------

# NIP-01: kind 0 = metadata, kind 1 = text note, kind 4 = encrypted DM
KIND_META = 0
KIND_TEXT_NOTE = 1
KIND_ENCRYPTED_DM = 4
KIND_NARADA_EMAIL = 1050  # Narada-specific: email message relayed via Nostr

# Narada uses a custom event kind for email messages to avoid colliding
# with standard Nostr kinds. This is registered here as a private kind
# in the 10000-19999 range (NIP-01: "replaceable" events, but we use
# it as an application-specific kind).
#
# The kind 1050 carries an encrypted NaradaBody (NaradaBody JSON) inside
# the Nostr event content. The encryption follows NIP-04 for 1:1 DMs
# and NIP-44 for group messages.


# --- Event ------------------------------------------------------------------


@dataclass
class NostrEvent:
    """A Nostr event (NIP-01).

    Fields:

    * ``id`` — 32-byte hex SHA-256 hash of the serialized event
    * ``pubkey`` — 32-byte hex public key of the author
    * ``created_at`` — unix timestamp (seconds)
    * ``kind`` — event kind (0=meta, 1=text, 4=encrypted DM, 1050=narada email)
    * ``tags`` — list of tag arrays (e.g. [["p", "<pubkey>"], ["e", "<event_id>"]])
    * ``content`` — the event content (plaintext or encrypted)
    * ``sig`` — 64-byte hex Ed25519 signature
    """

    id: str = ""
    pubkey: str = ""
    created_at: int = 0
    kind: int = KIND_TEXT_NOTE
    tags: list[list[str]] = field(default_factory=list)
    content: str = ""
    sig: str = ""

    def serialized(self) -> str:
        """NIP-01: Serialize the event for id computation and signing.

        The serialization is: [0, "pubkey", created_at, kind, tags, content]
        encoded as a canonical JSON array.
        """
        return json.dumps(
            [0, self.pubkey, self.created_at, self.kind, self.tags, self.content],
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def compute_id(self) -> str:
        """Compute the event id as a 32-byte hex SHA-256 of the serialized event."""
        serialized = self.serialized()
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the event to a JSON-compatible dict."""
        return {
            "id": self.id,
            "pubkey": self.pubkey,
            "created_at": self.created_at,
            "kind": self.kind,
            "tags": self.tags,
            "content": self.content,
            "sig": self.sig,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NostrEvent:
        """Deserialize an event from a dict (e.g. from JSON)."""
        return cls(
            id=str(data.get("id", "")),
            pubkey=str(data.get("pubkey", "")),
            created_at=int(data.get("created_at", 0)),
            kind=int(data.get("kind", 1)),
            tags=[list(t) for t in data.get("tags", [])],
            content=str(data.get("content", "")),
            sig=str(data.get("sig", "")),
        )

    @classmethod
    def from_json(cls, json_str: str) -> NostrEvent:
        """Deserialize an event from a JSON string."""
        return cls.from_dict(json.loads(json_str))

    def to_json(self) -> str:
        """Serialize the event to a JSON string."""
        return json.dumps(self.to_dict(), separators=(",", ":"), ensure_ascii=False)


# --- Event creation and verification ----------------------------------------


def create_event(
    identity: NostrIdentity,
    *,
    kind: int = KIND_TEXT_NOTE,
    content: str = "",
    tags: Optional[list[list[str]]] = None,
    created_at: Optional[int] = None,
) -> NostrEvent:
    """Create a signed Nostr event.

    The event is signed with the identity's Ed25519 key. The event id
    is computed from the serialized event (NIP-01).

    Parameters
    ----------
    identity:
        The signing identity.
    kind:
        Event kind. Use KIND_ENCRYPTED_DM (4) for encrypted DMs,
        KIND_NARADA_EMAIL (1050) for Narada email messages.
    content:
        Event content. For encrypted events, pass the ciphertext.
    tags:
        Optional tags. Each tag is a list of strings.
    created_at:
        Optional unix timestamp. Defaults to current time.

    Returns
    -------
    NostrEvent
        The signed event ready for relay submission.
    """
    now = int(time.time()) if created_at is None else int(created_at)
    pubkey = identity.public_key_hex

    event = NostrEvent(
        id="",
        pubkey=pubkey,
        created_at=now,
        kind=kind,
        tags=tags or [],
        content=content,
        sig="",
    )

    # Compute id
    event.id = event.compute_id()

    # Sign the event id (NIP-01: sign the hex id string)
    sig_bytes = identity.sign(event.id.encode("utf-8"))
    event.sig = sig_bytes.hex()

    return event


def verify_event(event: NostrEvent) -> bool:
    """Verify a Nostr event's id and signature.

    Checks:
    1. The event id matches the SHA-256 of the serialized event.
    2. The Ed25519 signature over the event id is valid.

    Returns True if both checks pass.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    # Check id
    computed_id = event.compute_id()
    if computed_id != event.id:
        return False

    # Check signature
    if not event.pubkey or not event.sig:
        return False

    try:
        pubkey_bytes = bytes.fromhex(event.pubkey)
        if len(pubkey_bytes) != 32:
            return False
        sig_bytes = bytes.fromhex(event.sig)
        if len(sig_bytes) != 64:
            return False

        public_key = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
        public_key.verify(sig_bytes, event.id.encode("utf-8"))
        return True
    except Exception:
        return False


# --- Filters ----------------------------------------------------------------


@dataclass
class NostrFilter:
    """NIP-01 subscription filter.

    Used to subscribe to specific events from Nostr relays.
    All fields are optional; if omitted, they are not used as filters.
    """

    ids: Optional[list[str]] = None
    authors: Optional[list[str]] = None
    kinds: Optional[list[int]] = None
    since: Optional[int] = None
    until: Optional[int] = None
    limit: Optional[int] = None
    # NIP-01: #e and #p tag filters
    e_tag: Optional[list[str]] = None
    p_tag: Optional[list[str]] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the filter to a dict for relay communication."""
        d: dict[str, Any] = {}
        if self.ids is not None:
            d["ids"] = self.ids
        if self.authors is not None:
            d["authors"] = self.authors
        if self.kinds is not None:
            d["kinds"] = self.kinds
        if self.since is not None:
            d["since"] = self.since
        if self.until is not None:
            d["until"] = self.until
        if self.limit is not None:
            d["limit"] = self.limit
        if self.e_tag is not None:
            d["#e"] = self.e_tag
        if self.p_tag is not None:
            d["#p"] = self.p_tag
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NostrFilter:
        """Deserialize a filter from a dict."""
        return cls(
            ids=data.get("ids"),
            authors=data.get("authors"),
            kinds=data.get("kinds"),
            since=data.get("since"),
            until=data.get("until"),
            limit=data.get("limit"),
            e_tag=data.get("#e"),
            p_tag=data.get("#p"),
        )


def filter_for_dm(recipient_pubkey: str, sender_pubkey: Optional[str] = None) -> NostrFilter:
    """Create a filter for encrypted DMs (NIP-04, kind 4) addressed to a recipient.

    Parameters
    ----------
    recipient_pubkey:
        The hex public key of the recipient.
    sender_pubkey:
        Optional hex public key of a specific sender to filter for.
    """
    authors = [sender_pubkey] if sender_pubkey else None
    return NostrFilter(
        authors=authors,
        kinds=[KIND_ENCRYPTED_DM],
        p_tag=[recipient_pubkey],
    )


def filter_for_narada_email(
    recipient_pubkey: str,
    since: Optional[int] = None,
    limit: Optional[int] = None,
) -> NostrFilter:
    """Create a filter for Narada email events (kind 1050).

    Parameters
    ----------
    recipient_pubkey:
        The hex public key of the recipient.
    since:
        Only return events created after this unix timestamp.
    limit:
        Maximum number of events to return.
    """
    return NostrFilter(
        kinds=[KIND_NARADA_EMAIL],
        p_tag=[recipient_pubkey],
        since=since,
        limit=limit,
    )


__all__ = [
    "KIND_ENCRYPTED_DM",
    "KIND_META",
    "KIND_NARADA_EMAIL",
    "KIND_TEXT_NOTE",
    "NostrEvent",
    "NostrFilter",
    "create_event",
    "filter_for_dm",
    "filter_for_narada_email",
    "verify_event",
]
