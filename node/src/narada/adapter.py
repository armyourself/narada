"""Narada-protocol :class:`MailAdapter` implementation.

This is the production adapter for the Narada node. It implements
the same :class:`src.mail_abstraction.MailAdapter` interface as the
IMAP/SMTP adapter, but uses the Narada protocol for transport,
sealing, signing, and the local outbox for retry.

Today the adapter is wired for the Phase 2 MVP:

* It can ``send_message`` to a recipient identified by their
  ``narada1...`` public id. The recipient's base URL is looked up in
  the :class:`NaradaDirectory`. If the lookup fails, the message
  is queued in the :class:`Outbox`.
* ``fetch_messages`` reads from the per-account mailbox JSONL file
  (the same store the receiver writes to).
* ``list_folders`` returns a single ``Narada`` folder.
* ``watch`` is a polling stub; the Narada node today has no
  push channel (Phase 4+ will add one).

The adapter is the seam between the Narada protocol implementation
and the rest of the node. Routers and clients keep using the
:class:`MailAdapter` interface; only the underlying transport
changes.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, Optional

from src.internal.file_system import FileObject, Root
from src.narada_identity.encoding import decode_public_id
from src.narada_identity.errors import NaradaIdentityError
from src.narada_identity.identity import NaradaIdentity
from src.narada_identity.keystore import NaradaKeystore, default_keystore
from src.mail_abstraction.base import (
    Address,
    Folder,
    MailAdapter,
    MailAdapterError,
    Message,
    MessageSource,
)

from .directory import NaradaDirectory
from .envelope import NaradaBody, NaradaEnvelope, NaradaEnvelopeError, make_envelope
from .inbox import NaradaInbox
from .outbox import Outbox, OutboxEntry
from .transport import HttpNaradaTransport, NaradaTransport, NaradaTransportError


class NaradaAdapter(MailAdapter):
    """Narada-protocol adapter.

    Parameters
    ----------
    account_id:
        The local account that owns this adapter instance. Used to
        load the Narada identity and to key the outbox / mailbox
        file.
    directory:
        Where to look up recipient public_id -> base_url mappings.
        Defaults to a fresh :class:`InMemoryDirectory` if not given;
        production code should pass a :class:`LocalContactList`.
    outbox:
        Where pending messages are queued. If None, a default
        :class:`Outbox` rooted under the node data directory is
        used.
    transport:
        The transport layer. Defaults to :class:`HttpNaradaTransport`
        for the Phase 2 MVP.
    keystore:
        Where the local account's identity is stored. Defaults to
        :func:`default_keystore`.
    """

    source = MessageSource.Narada

    def __init__(
        self,
        account_id: str,
        *,
        directory: Optional[NaradaDirectory] = None,
        outbox: Optional[Outbox] = None,
        transport: Optional[NaradaTransport] = None,
        keystore: Optional[NaradaKeystore] = None,
        data_dir: Optional[Path] = None,
    ) -> None:
        self._account_id = account_id
        self._directory = directory
        self._outbox = outbox
        self._transport = transport or HttpNaradaTransport()
        self._keystore = keystore or default_keystore()
        if data_dir is not None:
            self._data_dir = Path(data_dir)
        else:
            self._data_dir = self._default_data_dir()
        self._lock = threading.Lock()
        self._mailbox_path = self._data_dir / "etc" / f"mailbox.{_safe(self._account_id)}.jsonl"

    @staticmethod
    def _default_data_dir() -> Path:
        from src.consts import APP_NAME
        import os
        return Path(os.path.expanduser("~")) / f".{APP_NAME.lower()}"

    # --- Identity --------------------------------------------------------

    def _load_identity(self) -> NaradaIdentity:
        from src.narada_identity.identity import identity_from_keystore
        try:
            return identity_from_keystore(self._account_id, self._keystore)
        except NaradaIdentityError as exc:
            raise MailAdapterError(
                f"account {self._account_id!r} has no Narada identity: {exc}"
            ) from exc

    # --- Lifecycle -------------------------------------------------------

    def connect(self) -> tuple[bool, str]:
        # Narada transport is connectionless; success just means we
        # could load the local identity. Surface as a (bool, str) to
        # match the adapter contract.
        try:
            self._load_identity()
        except MailAdapterError as exc:
            return False, str(exc)
        return True, "Narada adapter ready."

    def disconnect(self) -> tuple[bool, str]:
        return True, "Narada adapter disconnected."

    def is_connected(self) -> bool:
        return True  # connectionless

    # --- Folders / fetch -------------------------------------------------

    def list_folders(self) -> list[Folder]:
        return [Folder(name="Narada", delimiter="/", is_selectable=True, children=[])]

    def fetch_messages(
        self,
        folder: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Message]:
        if not self._mailbox_path.exists():
            return []
        out: list[Message] = []
        try:
            with self._mailbox_path.open("r", encoding="utf-8") as f:
                lines = [ln for ln in f if ln.strip()]
        except OSError:
            return []
        # Newest first: reverse the line order, then apply offset/limit.
        for line in reversed(lines):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            out.append(_record_to_message(record, folder=folder or "Narada"))
        return out[offset:offset + limit]

    # --- Send -----------------------------------------------------------

    def send_message(
        self,
        *,
        from_address: Address,
        to_addresses: list[Address],
        subject: str,
        body: str,
        cc: Optional[list[Address]] = None,
        bcc: Optional[list[Address]] = None,  # accepted for adapter parity; not sent
        attachments: Optional[list[tuple[str, bytes]]] = None,  # accepted; not yet supported
        is_html: bool = False,  # accepted; not yet supported
    ) -> tuple[bool, str]:
        if not to_addresses:
            raise MailAdapterError("send_message requires at least one recipient")
        if len(to_addresses) > 1:
            # The Narada protocol is one envelope per recipient; for
            # the MVP we send one envelope per recipient.
            results: list[tuple[bool, str]] = []
            for r in to_addresses:
                ok, msg = self._send_one(
                    from_address=from_address,
                    to_address=r,
                    subject=subject,
                    body=body,
                    cc=cc,
                )
                results.append((ok, msg))
            return all(ok for ok, _ in results), "; ".join(m for _, m in results)

        return self._send_one(
            from_address=from_address,
            to_address=to_addresses[0],
            subject=subject,
            body=body,
            cc=cc,
        )

    def _send_one(
        self,
        *,
        from_address: Address,
        to_address: Address,
        subject: str,
        body: str,
        cc: Optional[list[Address]],
    ) -> tuple[bool, str]:
        recipient_public_id = to_address.address
        try:
            decode_public_id(recipient_public_id)
        except Exception as exc:
            raise MailAdapterError(f"recipient is not a Narada public id: {exc}") from exc

        sender = self._load_identity()
        narada_body = NaradaBody(
            subject=subject,
            sender=str(from_address),
            to=(str(to_address),),
            cc=tuple(str(c) for c in (cc or [])),
            body_text=body,
            sent_at=int(time.time()),
        )
        envelope = make_envelope(sender, recipient_public_id, narada_body)
        envelope_dict = envelope.as_dict()

        directory = self._ensure_directory()
        base_url = directory.lookup(recipient_public_id)
        if base_url is None:
            # Recipient is unknown: queue and let the user resolve it
            # later (or the directory learns about it through first
            # contact in a future phase).
            self._ensure_outbox().enqueue(
                account_id=self._account_id,
                recipient_public_id=recipient_public_id,
                envelope=envelope_dict,
            )
            return False, f"recipient {recipient_public_id} not in directory; queued in outbox"

        try:
            self._transport.send(base_url, envelope_dict)
            return True, f"delivered to {recipient_public_id}"
        except NaradaTransportError as exc:
            # Recipient was reachable but refused the message (4xx/5xx)
            # OR the network call failed. Either way, queue with
            # backoff so the user can see the failure and the outbox
            # can retry.
            self._ensure_outbox().enqueue(
                account_id=self._account_id,
                recipient_public_id=recipient_public_id,
                envelope=envelope_dict,
                first_attempt_delay_seconds=60,  # first retry in 1 minute
            )
            return False, f"delivery failed, queued for retry: {exc}"

    # --- Watch (polling stub) -------------------------------------------

    def watch(self, folder: str, on_new_message: Callable[[Message], None]) -> None:
        # The Narada node currently exposes a polling seam via
        # fetch_messages. Push / WebSocket will land in Phase 4+; for
        # now, the routers use the existing IMAP/Socket flow.
        raise MailAdapterError(
            "NaradaAdapter.watch is not implemented; the routers poll "
            "via fetch_messages for now (Phase 4+ will add push)."
        )

    # --- Outbox helpers (used by the drainer in main.py) ---------------

    def drain_outbox(self, *, max_per_account: int = 16) -> int:
        """Try to deliver every due outbox entry. Returns the number of attempts.

        Designed to be called by the FastAPI lifespan background task.
        """
        if self._outbox is None:
            return 0
        outbox = self._outbox
        sent = 0
        for account_id in outbox.list_all_accounts():
            for entry in outbox.list_due(account_id):
                if sent >= max_per_account:
                    return sent
                self._attempt_delivery(entry)
                sent += 1
        return sent

    def _attempt_delivery(self, entry: OutboxEntry) -> None:
        directory = self._ensure_directory()
        base_url = directory.lookup(entry.recipient_public_id)
        if base_url is None:
            # Still no directory entry; back off.
            self._outbox.mark_failed(
                entry.account_id,
                entry.message_id,
                error="recipient not in directory",
            )
            return
        try:
            self._transport.send(base_url, entry.envelope)
            self._outbox.mark_delivered(entry.account_id, entry.message_id)
        except NaradaTransportError as exc:
            self._outbox.mark_failed(
                entry.account_id,
                entry.message_id,
                error=str(exc),
            )

    # --- Lazy initialization --------------------------------------------

    def _ensure_directory(self) -> NaradaDirectory:
        if self._directory is None:
            from .directory import LocalContactList
            self._directory = LocalContactList(self._data_dir / "Narada" / "contacts.json")
        return self._directory

    def _ensure_outbox(self) -> Outbox:
        if self._outbox is None:
            self._outbox = Outbox(self._data_dir / "Narada")
        return self._outbox

    # --- Test hook -------------------------------------------------------

    @property
    def outbox(self) -> Optional[Outbox]:
        return self._outbox

    @property
    def directory(self) -> Optional[NaradaDirectory]:
        return self._directory

    def set_outbox(self, outbox: Outbox) -> None:
        self._outbox = outbox

    def set_directory(self, directory: NaradaDirectory) -> None:
        self._directory = directory

    def deliver_for_test(self, envelope_dict: Mapping[str, Any]) -> None:
        """Test-only entry point: receive an envelope without going through HTTP.

        Production code receives envelopes via the FastAPI router. Tests
        that wire the in-process transport directly into another adapter
        use this to avoid the HTTP roundtrip.
        """
        inbox = NaradaInbox(
            self._account_id,
            keystore=self._keystore,
            data_dir=self._data_dir,
        )
        env = NaradaEnvelope.from_dict(envelope_dict)
        try:
            inbox.receive(env)
        except NaradaEnvelopeError as exc:
            # Duplicate or already-seen; ignore for the test path.
            import sys
            print(f"[deliver_for_test] {self._account_id}: {exc}", file=sys.stderr)


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
        source=MessageSource.Narada,
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


def _safe(account_id: str) -> str:
    return "".join(c if c.isalnum() or c in "._@+-" else "_" for c in account_id) or "unknown"


__all__ = ["NaradaAdapter"]
