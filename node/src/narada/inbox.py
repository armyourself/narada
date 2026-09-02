"""Receiver-side helpers for incoming Narada envelopes (Phase 2 MVP).

A :class:`NaradaInbox` is the thing the HTTP router hands a raw
envelope to. It:

  1. Verifies the sender is known and the signature is valid
     (delegated to :func:`src.narada.envelope.open_envelope`).
  2. Decrypts the body.
  3. Persists the message into the recipient's account store, with
     ``source='narada'`` so the rest of the Narada node (and the
     desktop client) can render it as a Narada-delivered message.

Persistence uses the existing per-account mailbox store
(:class:`src.internal.account_manager.AccountManager`). The inbox
appends an :class:`src.modules.openmail.types.Email` entry that
matches the shape the client UI already expects.

The inbox also tracks ``seen_message_ids`` for replay-window
deduplication. The MVP uses an in-memory set scoped to a single
process; a follow-up will persist it.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional

from src.internal.account_manager import Account, AccountManager
from src.narada_identity.encoding import decode_public_id
from src.narada_identity.errors import NaradaIdentityError
from src.narada_identity.identity import NaradaIdentity
from src.narada_identity.keystore import NaradaKeystore, default_keystore

from .envelope import (
    NaradaBody,
    NaradaEnvelope,
    NaradaEnvelopeError,
    open_envelope,
)


class NaradaInbox:
    """Receiver-side helper for Narada messages.

    ``account_id`` is the local account that owns this inbox. The
    recipient's Narada identity is loaded from ``keystore`` on the
    fly; the caller is expected to have already generated it.

    ``data_dir`` is the node data directory; the inbox writes its
    mailbox JSONL under ``<data_dir>/etc/mailbox.<account>.jsonl``.
    Default is the same path the rest of the node uses
    (``~/.openmail/etc``).
    """

    def __init__(
        self,
        account_id: str,
        *,
        keystore: Optional[NaradaKeystore] = None,
        seen_path: Optional[Path] = None,
        data_dir: Optional[Path] = None,
    ) -> None:
        self._account_id = account_id
        self._keystore = keystore or default_keystore()
        self._seen_lock = threading.Lock()
        self._seen: dict[str, int] = {}  # message_id -> expires_at unix sec
        self._seen_path = seen_path
        self._load_seen()
        if data_dir is None:
            from src.consts import APP_NAME
            import os
            data_dir = Path(os.path.expanduser("~")) / f".{APP_NAME.lower()}"
        self._data_dir = Path(data_dir)
        self._mailbox_dir = self._data_dir / "etc"
        self._mailbox_path = self._mailbox_dir / f"mailbox.{_safe_account_id(account_id)}.jsonl"

    # --- Persistence of "seen" set ---------------------------------------

    def _load_seen(self) -> None:
        if self._seen_path is None or not self._seen_path.exists():
            return
        try:
            data = json.loads(self._seen_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(data, dict):
            return
        for k, v in data.items():
            try:
                self._seen[str(k)] = int(v)
            except (TypeError, ValueError):
                continue

    def _save_seen(self) -> None:
        if self._seen_path is None:
            return
        self._seen_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._seen_path.with_suffix(self._seen_path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._seen, sort_keys=True), encoding="utf-8")
        tmp.replace(self._seen_path)

    def _is_duplicate(
        self, sender_public_id: str, message_id: str, ttl_seconds: int
    ) -> bool:
        # Key on (sender, message_id): two different senders picking the
        # same UUID (vanishingly rare but cheap to defend against) would
        # otherwise be incorrectly deduped.
        key = f"{sender_public_id}|{message_id}"
        now = int(time.time())
        with self._seen_lock:
            # Drop expired entries.
            expired = [k for k, exp in self._seen.items() if exp < now]
            for k in expired:
                del self._seen[k]
            if key in self._seen:
                return True
            self._seen[key] = now + ttl_seconds
            self._save_seen()
            return False

    # --- Public API ------------------------------------------------------

    def load_identity(self) -> NaradaIdentity:
        """Load the recipient's Narada identity for this account."""
        from src.narada_identity.identity import identity_from_keystore

        try:
            return identity_from_keystore(self._account_id, self._keystore)
        except NaradaIdentityError as exc:
            raise NaradaEnvelopeError(
                f"account {self._account_id!r} has no narada identity"
            ) from exc

    def receive(
        self,
        envelope: NaradaEnvelope,
        *,
        seen_ttl_seconds: int = 5 * 60,
    ) -> tuple[NaradaBody, bool]:
        """Verify, decrypt, and persist ``envelope``.

        Returns ``(body, was_duplicate)``. ``was_duplicate`` is True
        if the message_id was already accepted within ``seen_ttl_seconds``;
        in that case the body is still returned (for the caller's
        convenience) but persistence is skipped.
        """
        identity = self.load_identity()
        # Pre-check: is this envelope even for us? Cheap, avoids loading
        # the keystore on a stray message.
        try:
            decode_public_id(envelope.recipient_public_id)
        except Exception as exc:
            raise NaradaEnvelopeError(f"invalid recipient public id: {exc}") from exc

        if envelope.recipient_public_id != identity.public_id:
            raise NaradaEnvelopeError("envelope addressed to a different recipient")

        is_dup = self._is_duplicate(
            envelope.sender_public_id, envelope.message_id, seen_ttl_seconds
        )
        if is_dup:
            # Still verify + decrypt so the caller has the body; just
            # do not persist again.
            body = open_envelope(envelope, identity)
            return body, True

        body = open_envelope(envelope, identity)
        self._persist(envelope, body)
        return body, False

    def _persist(self, envelope: NaradaEnvelope, body: NaradaBody) -> None:
        """Append the message to the account's mailbox store.

        The ``AccountManager`` exposes ``get``/``edit``/``add``/``remove``
        but no per-account "mailbox" table. Phase 2 uses a small JSONL
        file under ``<data_dir>/etc/mailbox.<account>.jsonl`` that the
        existing router surface can read. The desktop client already
        shows whatever is in the account's mailbox, so this slot-in
        keeps the UI working without change.
        """
        record = {
            "uid": envelope.message_id,
            "source": "narada",
            "sender": body.sender or envelope.sender_public_id,
            "receivers": ", ".join(body.to) if body.to else self._account_id,
            "to": list(body.to),
            "cc": list(body.cc),
            "date": str(body.sent_at or envelope.timestamp),
            "subject": body.subject,
            "body": body.body_text,
            "in_reply_to": "",
            "references": "",
            "list_unsubscribe": "",
            "list_unsubscribe_post": "",
            "flags": ["\\Seen"],
            "attachments": [],
            "message_id": f"<{envelope.message_id}@Narada>",
            "sender_public_id": envelope.sender_public_id,
            "received_at": int(time.time()),
        }
        line = json.dumps(record, separators=(",", ":"))

        # Append atomically: open in 'a' mode; single-line writes are
        # atomic on POSIX. On Windows the OS guarantees the write of a
        # short record is atomic for our size.
        self._mailbox_dir.mkdir(parents=True, exist_ok=True)
        with open(self._mailbox_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        # Also link the Narada public id to the account (idempotent).
        try:
            manager = AccountManager()
            if manager.is_exists(self._account_id):
                existing_account = manager.get(self._account_id, include_password=False)
                if existing_account is not None and existing_account.narada_identity_id != envelope.recipient_public_id:
                    manager.edit(
                        Account(
                            email_address=existing_account.email_address,
                            avatar=existing_account.avatar,
                            fullname=existing_account.fullname,
                            narada_identity_id=envelope.recipient_public_id,
                        )
                    )
        except Exception:
            # Linking is best-effort; the user can re-link later.
            pass


def _safe_account_id(account_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._@+-" else "_" for c in account_id)
    return safe or "unknown"


__all__ = ["NaradaInbox"]
