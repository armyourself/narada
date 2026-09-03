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
        rotation_store: Optional["KeyRotationStore"] = None,
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
        # Optional: rotation store. When provided, the inbox accepts
        # v=3 envelopes as key-update announcements (persisted via
        # the store) and v=1 envelopes whose sender has an active
        # rotation record are accepted under the new ed25519 key.
        # See protocol/identity.md for the on-the-wire rotation
        # design (Option A: X25519 preserved).
        self._rotation_store = rotation_store

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
    ) -> tuple[NaradaBody, bool, bool]:
        """Verify, decrypt, and persist ``envelope``.

        Returns ``(body, was_duplicate, is_key_update)``.
        ``is_key_update`` is True if the envelope was a v=3
        key-update announcement (in which case ``body`` is a
        sentinel NaradaBody and the rotation is persisted via
        the rotation store instead of the mailbox).

        ``was_duplicate`` is True if the message_id was already
        accepted within ``seen_ttl_seconds``; the body is still
        returned (for the caller's convenience) but persistence
        is skipped.

        On a v=1 envelope whose ``sender_public_id`` has an
        active rotation record, the inbox verifies the signature
        under the rotation's new ed25519 key. The body is
        decrypted with the recipient's identity (whose X25519
        key is unchanged by the rotation, so ECDH still works).
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

        # v=3: key-update announcement. Persist via the rotation
        # store, do NOT touch the mailbox.
        if envelope.v == 3:
            return self._receive_key_update(envelope)

        is_dup = self._is_duplicate(
            envelope.sender_public_id, envelope.message_id, seen_ttl_seconds
        )
        if is_dup:
            body = self._open_with_rotation(envelope, identity)
            return body, True, False

        body = self._open_with_rotation(envelope, identity)
        self._persist(envelope, body)
        return body, False, False

    def _open_with_rotation(
        self, envelope: NaradaEnvelope, identity: NaradaIdentity
    ) -> NaradaBody:
        """Open ``envelope`` with the recipient's identity, but fall
        back to the rotation's new ed25519 key if the standard
        signature verification fails and an active rotation record
        exists for ``envelope.sender_public_id``.

        The recipient's X25519 key is unchanged by rotation
        (Option A), so the body decryption path is unchanged. The
        signature, however, was made with the sender's NEW
        ed25519 key after rotation; we re-verify with that key
        when the rotation record is active.

        Raises :class:`NaradaEnvelopeError` if neither path
        verifies the signature.
        """
        from .envelope import _canonical_json
        from src.narada_identity.encoding import decode_public_id
        from src.narada_identity.keypair import verify_signature
        # Standard path.
        try:
            return open_envelope(envelope, identity)
        except NaradaEnvelopeError:
            pass  # try the rotation path

        # Rotation fallback.
        if self._rotation_store is None:
            raise NaradaEnvelopeError(
                "envelope signature does not verify under the prior key "
                "and no rotation store is configured"
            )
        rec = self._rotation_store.lookup(envelope.sender_public_id)
        if rec is None:
            raise NaradaEnvelopeError(
                "envelope signature does not verify under the prior key "
                "and no active rotation is recorded for this sender"
            )
        # Rebuild the canonical header bytes (same as in make_envelope).
        header_dict = {
            "v": envelope.v,
            "sender_public_id": envelope.sender_public_id,
            "recipient_public_id": envelope.recipient_public_id,
            "message_id": envelope.message_id,
            "timestamp": envelope.timestamp,
            "nonce": envelope.nonce,
        }
        header_bytes = _canonical_json(header_dict)
        _ver, new_ed_pub, _x_pub = decode_public_id(rec.new_public_id)
        if not verify_signature(new_ed_pub, envelope.signature, header_bytes):
            raise NaradaEnvelopeError(
                "envelope signature does not verify under either prior or new key"
            )
        # Signature verified under the new ed25519 key. The X25519
        # half of the recipient identity is unchanged by rotation
        # (Option A), so the body decryption in open_envelope
        # used the right X25519 key. Re-derive the body with the
        # standard recipient identity.
        return open_envelope(envelope, identity)

    def _receive_key_update(
        self, envelope: NaradaEnvelope
    ) -> tuple[NaradaBody, bool, bool]:
        """Handle a v=3 key-update envelope. Persist the rotation
        record and return a sentinel body.

        The dedup window is checked against the prior public id
        so that re-broadcasts of the same update are deduped.
        """
        from .key_update import open_key_update_envelope

        if self._rotation_store is None:
            raise NaradaEnvelopeError(
                "v=3 envelope received but no rotation store is configured"
            )
        # A key update is addressed to a recipient; the
        # recipient opens it with their own identity.
        identity = self.load_identity()
        body = open_key_update_envelope(envelope, identity)
        # Reject updates whose not_after has already passed: the
        # rotation window has closed and the announcement is no
        # longer useful. Accepting it would extend trust to a key
        # that was supposed to be off the air.
        import time as _t
        if int(body.not_after) < int(_t.time()):
            raise NaradaEnvelopeError(
                "key-update envelope is past its not_after"
            )
        is_dup = self._is_duplicate(
            body.prior_public_id, envelope.message_id, 5 * 60
        )
        if is_dup:
            return body, True, True
        # Persist. record() overwrites any prior record for the
        # same prior_public_id.
        self._rotation_store.record(
            prior_public_id=body.prior_public_id,
            new_public_id=body.new_public_id,
            not_after=body.not_after,
        )
        return body, False, True
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
