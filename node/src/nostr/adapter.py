"""Nostr adapter implementing the MailAdapter interface.

This is the production adapter for the Nostr transport. It implements
the same :class:`src.mail_abstraction.MailAdapter` interface as the
IMAP/SMTP adapter and the legacy Narada adapter.

The adapter translates between:

* NaradaMessage (email semantics) ↔ NostrEvent (Nostr transport)
* NaradaIdentity ↔ NostrIdentity
* MailAdapter methods ↔ Nostr relay operations

Architecture::

    NostrAdapter
        │
        ├── NostrIdentity (sign/verify)
        ├── NostrRelayPool (publish/subscribe)
        ├── NaradaInbox (persist messages)
        └── Outbox (retry failed delivery)

The adapter supports:

* Sending encrypted Narada email messages via Nostr relays
* Receiving and decrypting Nostr events into Narada messages
* Multiple relay failover
* Duplicate event detection
* Offline message delivery (relays as store-and-forward)
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from src.mail_abstraction.base import (
    Address,
    Folder,
    MailAdapter,
    MailAdapterError,
    Message,
    MessageSource,
)

from .config import NostrConfig, DEFAULT_RELAYS, NARADA_EMAIL_KIND
from .events import (
    NostrEvent,
    NostrFilter,
    create_event,
    verify_event,
    filter_for_narada_email,
    KIND_NARADA_EMAIL,
    KIND_ENCRYPTED_DM,
)
from .identity import NostrIdentity, generate_nostr_identity
from .relay import RelayPool


class NostrAdapter(MailAdapter):
    """Nostr-protocol adapter implementing the MailAdapter interface.

    Translates between Narada email semantics and Nostr event transport.
    Supports multiple relays, encryption, and offline delivery.

    Parameters
    ----------
    account_id:
        The local account that owns this adapter instance.
    identity:
        The Nostr identity for signing events. If None, loaded from
        the Narada keystore for this account.
    config:
        Nostr transport configuration. Defaults to NostrConfig.default().
    relay_pool:
        Optional pre-configured relay pool. If None, created from config.
    data_dir:
        Node data directory for mailbox persistence.
    """

    source = MessageSource.Nostr

    def __init__(
        self,
        account_id: str,
        *,
        identity: Optional[NostrIdentity] = None,
        config: Optional[NostrConfig] = None,
        relay_pool: Optional[RelayPool] = None,
        data_dir: Optional[Path] = None,
    ) -> None:
        self._account_id = account_id
        self._identity = identity
        self._config = config or NostrConfig.default()
        self._relay_pool = relay_pool or RelayPool(
            self._config.relay_urls,
            timeout_seconds=self._config.timeout_seconds,
        )
        self._lock = threading.Lock()
        if data_dir is not None:
            self._data_dir = Path(data_dir)
        else:
            self._data_dir = self._default_data_dir()
        self._mailbox_dir = self._data_dir / "etc"
        self._mailbox_path = self._mailbox_dir / f"mailbox.{_safe(self._account_id)}.jsonl"
        self._connected = False
        self._outbox = None
        self._subscription_id: Optional[str] = None

    @staticmethod
    def _default_data_dir() -> Path:
        from src.consts import APP_NAME
        import os
        return Path(os.path.expanduser("~")) / f".{APP_NAME.lower()}"

    # --- Identity --------------------------------------------------------

    def _ensure_identity(self) -> NostrIdentity:
        """Load or generate the Nostr identity for this account.

        If the account has an existing Narada identity, the Nostr identity
        is derived from the same Ed25519 seed (enabling migration).
        """
        if self._identity is not None:
            return self._identity

        try:
            from src.narada_identity.identity import identity_from_keystore
            from src.narada_identity.keystore import default_keystore
            from .identity import nostr_identity_from_narada_seed

            keystore = default_keystore()
            narada_identity = identity_from_keystore(self._account_id, keystore)
            # Derive Nostr identity from the Narada Ed25519 seed
            self._identity = nostr_identity_from_narada_seed(narada_identity.keypair.ed25519_seed)
        except Exception:
            # No existing Narada identity: generate a new Nostr identity
            self._identity = generate_nostr_identity()

        return self._identity

    # --- Lifecycle -------------------------------------------------------

    def connect(self) -> tuple[bool, str]:
        """Connect to Nostr relays and start listening for messages."""
        try:
            self._ensure_identity()
            # Connect to relays (async in thread)
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                connected = loop.run_until_complete(self._relay_pool.connect_all())
            finally:
                loop.close()

            if connected == 0:
                return False, "Could not connect to any Nostr relays"

            self._connected = True
            return True, f"Connected to {connected}/{len(self._relay_pool.relays)} Nostr relays"
        except Exception as exc:
            return False, f"Nostr connect failed: {exc}"

    def disconnect(self) -> tuple[bool, str]:
        """Disconnect from all Nostr relays."""
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self._relay_pool.disconnect_all())
            finally:
                loop.close()
            self._connected = False
            return True, "Disconnected from Nostr relays"
        except Exception as exc:
            return False, f"Disconnect failed: {exc}"

    def is_connected(self) -> bool:
        return self._connected and self._relay_pool.connected_count() > 0

    # --- Folders / fetch -------------------------------------------------

    def list_folders(self) -> list[Folder]:
        return [Folder(name="nostr", delimiter="/", is_selectable=True, children=[])]

    def fetch_messages(
        self,
        folder: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Message]:
        """Fetch Narada email messages stored locally.

        Messages were received from Nostr relays and persisted to the
        mailbox JSONL file (same as the legacy Narada adapter).
        """
        if not self._mailbox_path.exists():
            return []
        out: list[Message] = []
        try:
            with self._mailbox_path.open("r", encoding="utf-8") as f:
                lines = [ln for ln in f if ln.strip()]
        except OSError:
            return []
        for line in reversed(lines):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            out.append(_record_to_message(record, folder=folder or "nostr"))
        return out[offset:offset + limit]

    # --- Send -----------------------------------------------------------

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
        """Send a Narada email message via Nostr relays.

        The message is:

        1. Wrapped in a NaradaBody
        2. Encrypted with NIP-04 or NIP-44
        3. Signed as a Nostr event (kind 1050)
        4. Published to configured Nostr relays
        """
        if not to_addresses:
            raise MailAdapterError("send_message requires at least one recipient")

        identity = self._ensure_identity()

        results: list[tuple[bool, str]] = []
        for to_addr in to_addresses:
            ok, msg = self._send_one(
                identity=identity,
                from_address=from_address,
                to_address=to_addr,
                subject=subject,
                body=body,
                cc=cc,
            )
            results.append((ok, msg))

        return all(ok for ok, _ in results), "; ".join(m for _, m in results)

    def _send_one(
        self,
        *,
        identity: NostrIdentity,
        from_address: Address,
        to_address: Address,
        subject: str,
        body: str,
        cc: list[Address] | None,
    ) -> tuple[bool, str]:
        """Send to a single recipient via Nostr."""
        recipient_pubkey_hex = to_address.address

        # Validate that the recipient address looks like a hex pubkey
        try:
            bytes.fromhex(recipient_pubkey_hex)
            if len(recipient_pubkey_hex) != 64:
                return False, f"Invalid recipient pubkey length: {recipient_pubkey_hex[:16]}..."
        except ValueError:
            return False, f"Recipient is not a valid Nostr pubkey: {recipient_pubkey_hex[:16]}..."

        # Build NaradaBody
        narada_body = {
            "subject": subject,
            "sender": str(from_address),
            "to": [str(to_address)],
            "cc": [str(c) for c in (cc or [])],
            "body_text": body,
            "sent_at": int(time.time()),
        }

        # Encrypt the body
        from .encryption import nip04_encrypt, nip44_encrypt, _x25519_public_from_ed25519
        body_json = json.dumps(narada_body, separators=(",", ":"))
        # NIP-04 uses Ed25519 seed for signing + X25519 public for encryption
        sender_ed25519_seed = identity._private_key_bytes
        recipient_x25519_pub = _x25519_public_from_ed25519(
            bytes.fromhex(recipient_pubkey_hex)  # Nostr pubkey is Ed25519
        )

        if self._config.encryption == "nip44":
            ciphertext = nip44_encrypt(
                body_json,
                sender_ed25519_seed,
                recipient_x25519_pub,
            )
            content = ciphertext.hex()
        else:
            content = nip04_encrypt(
                body_json,
                sender_ed25519_seed,
                recipient_x25519_pub,
            )

        # Create Nostr event (kind 1050 = Narada email)
        event = create_event(
            identity,
            kind=KIND_NARADA_EMAIL,
            content=content,
            tags=[["p", recipient_pubkey_hex]],
        )

        # Publish to relays
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            success, msg = loop.run_until_complete(
                self._relay_pool.publish_with_failover(event)
            )
        finally:
            loop.close()

        if success:
            return True, f"Published to Nostr relays for {recipient_pubkey_hex[:16]}..."
        else:
            return False, f"Failed to publish to Nostr relays: {msg}"

    # --- Receive --------------------------------------------------------

    def subscribe_for_messages(
        self,
        on_message: Optional[Callable[[Message], None]] = None,
    ) -> str:
        """Subscribe to incoming Narada email events on Nostr relays.

        Returns a subscription ID that can be used to unsubscribe.
        """
        identity = self._ensure_identity()
        sub_id = f"narada_{self._account_id}_{int(time.time())}"

        filters = [
            filter_for_narada_email(
                identity.public_key_hex,
                limit=100,
            )
        ]

        import asyncio
        loop = asyncio.new_event_loop()
        try:
            # Use a callback that decrypts and persists the event
            def _on_event(event: NostrEvent) -> None:
                self._handle_incoming_event(event, identity)
                if on_message:
                    msg = self._event_to_message(event)
                    if msg:
                        on_message(msg)

            loop.run_until_complete(
                self._relay_pool.subscribe(sub_id, filters, on_event=_on_event)
            )
        finally:
            loop.close()

        self._subscription_id = sub_id
        return sub_id

    def _handle_incoming_event(self, event: NostrEvent, identity: NostrIdentity) -> None:
        """Handle an incoming Nostr event: verify, decrypt, persist."""
        # Verify the event
        if not verify_event(event):
            return

        # Decrypt the content
        try:
            from .encryption import _x25519_public_from_ed25519
            sender_x25519_pub = _x25519_public_from_ed25519(bytes.fromhex(event.pubkey))
            recipient_ed25519_seed = identity._private_key_bytes

            if self._config.encryption == "nip44":
                from .encryption import nip44_decrypt
                ciphertext = bytes.fromhex(event.content)
                plaintext = nip44_decrypt(
                    ciphertext,
                    recipient_ed25519_seed,
                    sender_x25519_pub,
                )
            else:
                from .encryption import nip04_decrypt
                plaintext = nip04_decrypt(
                    event.content,
                    recipient_ed25519_seed,
                    sender_x25519_pub,
                )
            body_data = json.loads(plaintext)
        except Exception:
            return

        # Persist to mailbox
        self._persist_event(event, body_data)

    def _event_to_message(self, event: NostrEvent) -> Optional[Message]:
        """Convert a Nostr event to a MailAdapter Message."""
        try:
            from .encryption import _x25519_public_from_ed25519
            identity = self._ensure_identity()
            sender_x25519_pub = _x25519_public_from_ed25519(bytes.fromhex(event.pubkey))
            recipient_ed25519_seed = identity._private_key_bytes

            if self._config.encryption == "nip44":
                from .encryption import nip44_decrypt
                ciphertext = bytes.fromhex(event.content)
                plaintext = nip44_decrypt(
                    ciphertext,
                    recipient_ed25519_seed,
                    sender_x25519_pub,
                )
            else:
                from .encryption import nip04_decrypt
                plaintext = nip04_decrypt(
                    event.content,
                    recipient_ed25519_seed,
                    sender_x25519_pub,
                )
            body_data = json.loads(plaintext)
        except Exception:
            return None

        return Message(
            uid=event.id,
            folder="nostr",
            source=MessageSource.Narada,
            subject=body_data.get("subject", ""),
            from_address=_address_from_string(body_data.get("sender", "")),
            to_addresses=[_address_from_string(t) for t in body_data.get("to", [])],
            date=str(body_data.get("sent_at", "")),
            preview=body_data.get("body_text", "")[:140] if body_data.get("body_text") else None,
            has_attachments=False,
            is_read=False,
            is_flagged=False,
            raw=None,
        )

    def _persist_event(self, event: NostrEvent, body_data: dict) -> None:
        """Persist a received Nostr event to the mailbox JSONL file."""
        record = {
            "uid": event.id,
            "source": "nostr",
            "sender": body_data.get("sender", ""),
            "receivers": ", ".join(body_data.get("to", [])) or self._account_id,
            "to": body_data.get("to", []),
            "cc": body_data.get("cc", []),
            "date": str(body_data.get("sent_at", "")),
            "subject": body_data.get("subject", ""),
            "body": body_data.get("body_text", ""),
            "in_reply_to": "",
            "references": "",
            "list_unsubscribe": "",
            "list_unsubscribe_post": "",
            "flags": ["\\Seen"],
            "attachments": [],
            "message_id": f"<{event.id}@Nostr>",
            "nostr_event_id": event.id,
            "nostr_pubkey": event.pubkey,
            "nostr_kind": event.kind,
            "received_at": int(time.time()),
        }
        line = json.dumps(record, separators=(",", ":"))
        self._mailbox_dir.mkdir(parents=True, exist_ok=True)
        with open(self._mailbox_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    # --- Watch (polling) ------------------------------------------------

    def watch(self, folder: str, on_new_message: Callable[[Message], None]) -> None:
        """Watch for new messages via Nostr relay subscription."""
        self.subscribe_for_messages(on_message=on_new_message)

    # --- Relay management -----------------------------------------------

    async def _connect_relays(self) -> int:
        """Connect to all configured relays."""
        return await self._relay_pool.connect_all()

    async def _publish_event(self, event: NostrEvent) -> tuple[bool, str]:
        """Publish an event to the relay pool."""
        return await self._relay_pool.publish_with_failover(event)

    # --- Test hooks -----------------------------------------------------

    @property
    def relay_pool(self) -> RelayPool:
        return self._relay_pool

    @property
    def identity(self) -> Optional[NostrIdentity]:
        return self._identity

    def set_identity(self, identity: NostrIdentity) -> None:
        self._identity = identity


# --- Helpers ----------------------------------------------------------------


def _safe(account_id: str) -> str:
    return "".join(c if c.isalnum() or c in "._@+-" else "_" for c in account_id) or "unknown"


def _address_from_string(value: str) -> Address:
    text = (value or "").strip()
    if not text:
        return Address(address="")
    if "<" in text and ">" in text:
        name_part, _, addr_part = text.partition("<")
        name = name_part.strip().strip('"') or None
        addr = (addr_part.split(">", 1)[0] or "").strip()
        return Address(address=addr, name=name)
    return Address(address=text)


def _record_to_message(record: dict, *, folder: str) -> Message:
    sender = str(record.get("sender", ""))
    to_field = record.get("to") or []
    if isinstance(to_field, str):
        to_addresses = [_address_from_string(t) for t in to_field.split(",") if t.strip()]
    else:
        to_addresses = [_address_from_string(str(t)) for t in to_field if t]
    return Message(
        uid=str(record.get("uid", "")),
        folder=folder,
        source=str(record.get("source", "nostr")),
        subject=str(record.get("subject", "")),
        from_address=_address_from_string(sender),
        to_addresses=to_addresses,
        date=str(record.get("date", "")),
        preview=(str(record.get("body", ""))[:140] if record.get("body") else None),
        has_attachments=bool(record.get("attachments")),
        is_read="\\Seen" in (record.get("flags") or []),
        is_flagged="\\Flagged" in (record.get("flags") or []),
        raw=None,
    )


__all__ = ["NostrAdapter"]
