"""Nostr adapter implementing the MailAdapter interface.

This is the production adapter for the Nostr transport. It implements
the same :class:`src.mail_abstraction.MailAdapter` interface as the
IMAP/SMTP adapter.

The adapter translates between:

* Email semantics <-> NostrEvent (Nostr transport)
* MailAdapter methods <-> Nostr relay operations

Architecture::

    NostrAdapter
        |
        +-- NostrIdentity (sign/verify)
        +-- NostrRelayPool (publish/subscribe)
        +-- Mailbox persistence (JSONL)

The adapter supports:

* Sending encrypted email messages via Nostr relays
* Receiving and decrypting Nostr events into email messages
* Multiple relay failover
* Duplicate event detection
* Offline message delivery (relays as store-and-forward)
"""

from __future__ import annotations

import asyncio
import concurrent.futures
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

from .config import NostrConfig, DEFAULT_RELAYS, EMAIL_KIND
from .events import (
    NostrEvent,
    NostrFilter,
    create_event,
    verify_event,
    filter_for_email,
    KIND_EMAIL,
    KIND_ENCRYPTED_DM,
)
from .identity import NostrIdentity, generate_nostr_identity
from .relay import RelayPool


class NostrAdapter(MailAdapter):
    """Nostr-protocol adapter implementing the MailAdapter interface.

    Translates between email semantics and Nostr event transport.
    Supports multiple relays, encryption, and offline delivery.

    Parameters
    ----------
    account_id:
        The local account that owns this adapter instance.
    identity:
        The Nostr identity for signing events. If None, a new identity
        is generated for this account.
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
        # Persistent background event loop: every relay socket this
        # adapter opens must live on ONE loop for its whole lifetime.
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_guard = threading.Lock()
        # Event-id dedup: relays replay stored events on every REQ, so
        # without this each restart/reconnect would re-append history.
        self._seen_event_ids: Optional[set[str]] = None
        self._persist_lock = threading.Lock()

    @staticmethod
    def _default_data_dir() -> Path:
        from src.consts import APP_NAME
        import os
        return Path(os.path.expanduser("~")) / f".{APP_NAME.lower()}"

    # --- Identity --------------------------------------------------------

    def _ensure_identity(self) -> NostrIdentity:
        """Load or generate the Nostr identity for this account."""
        if self._identity is not None:
            return self._identity
        self._identity = generate_nostr_identity()
        return self._identity

    # --- Background event loop ---------------------------------------------

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """Return the adapter's persistent background event loop.

        All relay I/O runs on this single loop for the adapter's
        lifetime.  The previous pattern (``asyncio.new_event_loop()``
        per call, then ``loop.close()``) left every opened WebSocket
        bound to an already-closed loop: publishes and subscriptions
        silently failed while ``status.connected`` still read True.
        """
        loop = self._loop
        if (
            loop is not None
            and not loop.is_closed()
            and self._loop_thread is not None
            and self._loop_thread.is_alive()
        ):
            return loop

        with self._loop_guard:
            loop = self._loop
            if (
                loop is not None
                and not loop.is_closed()
                and self._loop_thread is not None
                and self._loop_thread.is_alive()
            ):
                return loop

            loop = asyncio.new_event_loop()
            started = threading.Event()

            def _run_loop() -> None:
                asyncio.set_event_loop(loop)
                started.set()
                try:
                    loop.run_forever()
                finally:
                    try:
                        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                        for task in pending:
                            task.cancel()
                        if pending:
                            loop.run_until_complete(
                                asyncio.gather(*pending, return_exceptions=True)
                            )
                    finally:
                        loop.close()

            thread = threading.Thread(
                target=_run_loop,
                name=f"nostr-adapter-{_safe(self._account_id)}",
                daemon=True,
            )
            thread.start()
            started.wait(timeout=5)
            self._loop = loop
            self._loop_thread = thread
            return loop

    def _run(self, coro: Any, *, timeout: float = 60.0) -> Any:
        """Run *coro* on the background loop and block for its result."""
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return future.result(timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise MailAdapterError(
                f"Nostr operation timed out after {timeout:.0f}s"
            ) from None

    def _operation_timeout(self) -> float:
        """Room for every relay in the pool to connect/publish in turn."""
        return max(30.0, self._config.timeout_seconds * (len(self._relay_pool.relays) + 1))

    def _shutdown_loop(self) -> None:
        """Stop the background loop thread and release its resources."""
        with self._loop_guard:
            loop, thread = self._loop, self._loop_thread
            self._loop = None
            self._loop_thread = None
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(loop.stop)
        except RuntimeError:
            return  # loop already closed
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)

    # --- Lifecycle -------------------------------------------------------

    def connect(self) -> tuple[bool, str]:
        """Connect to Nostr relays and start listening for messages.

        On success the inbox subscription is established immediately,
        so events addressed to this identity are persisted as soon as
        the application boots -- no caller has to trigger receiving.
        """
        try:
            self._ensure_identity()
            connected = self._run(
                self._relay_pool.connect_all(),
                timeout=self._operation_timeout(),
            )

            if connected == 0:
                self._shutdown_loop()
                return False, "Could not connect to any Nostr relays"

            self._connected = True
            try:
                self.subscribe_for_messages()
            except Exception as exc:
                # Transport is up; receiving will be retried on the next
                # explicit subscribe()/watch() call.
                print(f"Nostr inbox subscription failed for {self._account_id}: {exc}")
            return True, f"Connected to {connected}/{len(self._relay_pool.relays)} Nostr relays"
        except Exception as exc:
            return False, f"Nostr connect failed: {exc}"

    def disconnect(self) -> tuple[bool, str]:
        """Disconnect from all Nostr relays and stop the background loop."""
        try:
            if self._subscription_id is not None:
                try:
                    self._run(
                        self._relay_pool.unsubscribe_all(self._subscription_id),
                        timeout=30.0,
                    )
                except Exception:
                    pass
                self._subscription_id = None
            self._run(self._relay_pool.disconnect_all(), timeout=30.0)
            self._connected = False
            return True, "Disconnected from Nostr relays"
        except Exception as exc:
            return False, f"Disconnect failed: {exc}"
        finally:
            self._shutdown_loop()

    def is_connected(self) -> bool:
        return self._connected and self._relay_pool.connected_count() > 0

    # --- Folders / fetch -------------------------------------------------

    def list_folders(self) -> list[Folder]:
        return [Folder(name="nostr", delimiter="/", is_selectable=True, children=[])]

    def _read_records(self) -> list[dict]:
        """All mailbox JSONL records, oldest first."""
        if not self._mailbox_path.exists():
            return []
        try:
            with self._mailbox_path.open("r", encoding="utf-8") as f:
                lines = [ln for ln in f if ln.strip()]
        except OSError:
            return []
        records: list[dict] = []
        for line in lines:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    def fetch_records(self, *, limit: int = 5000) -> list[dict]:
        """Raw mailbox records (newest first) with full bodies.

        Used by API projections that need the complete message text
        (``fetch_messages`` only carries a 140-char preview).
        """
        return list(reversed(self._read_records()))[:limit]

    def fetch_messages(
        self,
        folder: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Message]:
        """Fetch email messages stored locally.

        Messages were received from Nostr relays and persisted to the
        mailbox JSONL file.
        """
        out: list[Message] = [
            _record_to_message(record, folder=folder or "nostr")
            for record in reversed(self._read_records())
        ]
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
        """Send an email message via Nostr relays.

        The message is:

        1. Wrapped in an email body dict
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

        try:
            bytes.fromhex(recipient_pubkey_hex)
            if len(recipient_pubkey_hex) != 64:
                return False, f"Invalid recipient pubkey length: {recipient_pubkey_hex[:16]}..."
        except ValueError:
            return False, f"Recipient is not a valid Nostr pubkey: {recipient_pubkey_hex[:16]}..."

        email_body = {
            "subject": subject,
            "sender": str(from_address),
            "to": [str(to_address)],
            "cc": [str(c) for c in (cc or [])],
            "body_text": body,
            "sent_at": int(time.time()),
        }

        from .encryption import nip04_encrypt, nip44_encrypt, _x25519_public_from_ed25519_public
        body_json = json.dumps(email_body, separators=(",", ":"))
        sender_ed25519_seed = identity._private_key_bytes
        recipient_x25519_pub = _x25519_public_from_ed25519_public(
            bytes.fromhex(recipient_pubkey_hex)
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

        event = create_event(
            identity,
            kind=KIND_EMAIL,
            content=content,
            tags=[["p", recipient_pubkey_hex]],
        )

        success, msg = self._run(
            self._relay_pool.publish_with_failover(event),
            timeout=self._operation_timeout(),
        )

        if success:
            return True, f"Published to Nostr relays for {recipient_pubkey_hex[:16]}..."
        else:
            return False, f"Failed to publish to Nostr relays: {msg}"

    # --- Receive --------------------------------------------------------

    def subscribe_for_messages(
        self,
        on_message: Optional[Callable[[Message], None]] = None,
    ) -> str:
        """Subscribe to incoming email events on Nostr relays.

        Returns a subscription ID that can be used to unsubscribe.
        The inbox subscription (no callback) is established once and
        reused; callers that want push notifications pass *on_message*
        and get their own subscription.
        """
        if on_message is None and self._subscription_id is not None:
            return self._subscription_id

        identity = self._ensure_identity()
        sub_id = f"nostr_{self._account_id}_{int(time.time())}"

        filters = [
            filter_for_email(
                identity.public_key_hex,
                limit=100,
            )
        ]

        def _on_event(event: NostrEvent) -> None:
            self._handle_incoming_event(event, identity)
            if on_message:
                msg = self._event_to_message(event)
                if msg:
                    on_message(msg)

        self._run(
            self._relay_pool.subscribe(sub_id, filters, on_event=_on_event),
            timeout=self._operation_timeout(),
        )
        if on_message is None:
            self._subscription_id = sub_id
        return sub_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe a subscription created by subscribe_for_messages()."""
        try:
            self._run(
                self._relay_pool.unsubscribe_all(subscription_id),
                timeout=30.0,
            )
            if self._subscription_id == subscription_id:
                self._subscription_id = None
            return True
        except Exception:
            return False

    # --- Runtime relay management ----------------------------------------

    def add_relay(self, url: str) -> tuple[bool, str]:
        """Add *url* to this adapter's pool, connect it, and extend the
        inbox subscription so a runtime-added relay starts delivering
        without an app restart.

        Thread-safe: every relay operation is marshalled onto the
        adapter's persistent background loop.
        """
        try:
            return self._run(
                self._add_relay_async(url),
                timeout=self._operation_timeout(),
            )
        except Exception as exc:
            return False, f"Failed to add relay: {exc}"

    async def _add_relay_async(self, url: str) -> tuple[bool, str]:
        normalized = url.rstrip("/")
        if any(
            relay.url.lower() == normalized.lower()
            for relay in self._relay_pool.relays
        ):
            return False, f"Relay already in pool: {normalized}"

        self._relay_pool.add_relay(normalized)
        relay = self._relay_pool.relays[-1]
        connected_ok = await relay.connect()
        if not connected_ok:
            # Keep it listed — the persisted config owns it and the
            # listener will keep retrying; status surfaces the error.
            return False, (
                f"Relay added but connection failed: "
                f"{relay.status.last_error or 'unknown error'}"
            )

        identity = self._ensure_identity()
        filters = [
            filter_for_email(identity.public_key_hex, limit=100)
        ]

        def _on_event(event: NostrEvent) -> None:
            self._handle_incoming_event(event, identity)

        if self._subscription_id is None:
            # No live inbox session yet (first relay, or the boot-time
            # connect failed): establish receiving now.
            sub_id = f"nostr_{self._account_id}_{int(time.time())}"
            await self._relay_pool.subscribe(sub_id, filters, on_event=_on_event)
            self._subscription_id = sub_id
            self._connected = True
        else:
            # Existing session: re-issue the same subscription id — NIP-01
            # treats REQ as a replacement, so already-subscribed relays are
            # unaffected and the new relay starts delivering.
            await self._relay_pool.subscribe(
                self._subscription_id, filters, on_event=_on_event
            )
        return True, f"Connected to {normalized}"

    def remove_relay(self, url: str) -> tuple[bool, str]:
        """Disconnect and drop *url* from this adapter's pool.

        The socket is closed BEFORE the pool entry is removed — the pool's
        ``remove_relay`` only unlists, while the listener task would keep
        auto-reconnecting forever otherwise.
        """
        try:
            return self._run(self._remove_relay_async(url), timeout=30.0)
        except Exception as exc:
            return False, f"Failed to remove relay: {exc}"

    async def _remove_relay_async(self, url: str) -> tuple[bool, str]:
        normalized = url.rstrip("/")
        target = next(
            (
                relay
                for relay in self._relay_pool.relays
                if relay.url.lower() == normalized.lower()
            ),
            None,
        )
        if target is None:
            return False, f"Relay not in pool: {normalized}"
        await target.disconnect()
        self._relay_pool.remove_relay(target.url)
        return True, f"Removed {target.url}"

    def _handle_incoming_event(self, event: NostrEvent, identity: NostrIdentity) -> None:
        """Handle an incoming Nostr event: verify, decrypt, persist."""
        if not verify_event(event):
            return

        try:
            from .encryption import _x25519_public_from_ed25519_public
            sender_x25519_pub = _x25519_public_from_ed25519_public(bytes.fromhex(event.pubkey))
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

        self._persist_event(event, body_data)

    def _event_to_message(self, event: NostrEvent) -> Optional[Message]:
        """Convert a Nostr event to a MailAdapter Message."""
        try:
            from .encryption import _x25519_public_from_ed25519_public
            identity = self._ensure_identity()
            sender_x25519_pub = _x25519_public_from_ed25519_public(bytes.fromhex(event.pubkey))
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
            source=MessageSource.Nostr,
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

    def _load_seen_event_ids(self) -> set[str]:
        """Collect event ids already present in the mailbox (once)."""
        if self._seen_event_ids is not None:
            return self._seen_event_ids
        ids: set[str] = set()
        if self._mailbox_path.exists():
            try:
                with self._mailbox_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        event_id = record.get("nostr_event_id") or record.get("uid")
                        if event_id:
                            ids.add(str(event_id))
            except OSError:
                pass
        self._seen_event_ids = ids
        return ids

    def _persist_event(self, event: NostrEvent, body_data: dict) -> None:
        """Persist a received Nostr event to the mailbox JSONL file.

        Relays replay stored events on every subscription (REQ), and a
        single event may match several active subscriptions, so each
        event id is persisted exactly once.
        """
        with self._persist_lock:
            seen = self._load_seen_event_ids()
            if event.id in seen:
                return
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
                "message_id": f"<{event.id}@nostr>",
                "nostr_event_id": event.id,
                "nostr_pubkey": event.pubkey,
                "nostr_kind": event.kind,
                "received_at": int(time.time()),
            }
            line = json.dumps(record, separators=(",", ":"))
            self._mailbox_dir.mkdir(parents=True, exist_ok=True)
            with open(self._mailbox_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            seen.add(event.id)

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
