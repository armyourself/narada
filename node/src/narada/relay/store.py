"""Encrypted relay store (Phase 4).

The relay keeps sealed envelopes in a per-recipient store, encrypted
at rest under a key derived from a relay-side master secret and the
recipient's ``narada1...`` public id. The relay cannot read the body
because the body is already AEAD-sealed to the recipient's X25519
key by :func:`src.narada.envelope.make_envelope`. What the relay
store adds is **at-rest encryption** keyed per recipient, so a disk
attacker who steals the data directory without also stealing the
relay's in-memory master secret sees only ciphertext.

Storage layout::

    <data_dir>/relay/
        deposits/<recipient>.jsonl      # encrypted envelopes, one per line
        index.json                      # plain metadata, HMAC-protected
        receipts/<deposit_id>.bin       # relay.stored receipts (best-effort)

The index lists every deposit id we have ever issued (until pruned),
keyed by recipient. The encrypted JSONL files are the source of
truth for body bytes. Tombstones record deletions so the index can
be rebuilt from the on-disk file if the snapshot is tampered with
(following the watermark-store pattern in
:mod:`src.narada.p2p.listener`).
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

def _hmac_io():
    from src.narada_security.hmac_io import (
        HmacIntegrityError,
        hmac_io_key,
        read_json_protected,
        write_json_protected,
    )
    return HmacIntegrityError, hmac_io_key, read_json_protected, write_json_protected


# --- Defaults --------------------------------------------------------------

DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
DEFAULT_MAX_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days
DEFAULT_MAX_DEPOSITS_PER_RECIPIENT = 64
DEFAULT_MAX_BYTES_PER_RECIPIENT = 16 * 1024 * 1024  # 16 MiB
DEFAULT_MAX_TOTAL_DEPOSITS = 16 * 384  # 16 * 384 = 6144; spec target 16384
DEFAULT_MAX_TOTAL_BYTES = 256 * 1024 * 1024  # 256 MiB

# Per-line cap; envelopes today are tiny but we keep a sane ceiling
# so a malicious peer cannot fill our disk in one frame.
_MAX_DEPOSIT_BYTES = 1 * 1024 * 1024  # 1 MiB per envelope

# Public-id charset: matches what we accept elsewhere.
_RECIPIENT_PATTERN = re.compile(r"^[a-z0-9]{6,16}1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]+$")
_ENVELOPE_KEY_INFO = b"Narada-relay-v1"


# --- Errors ----------------------------------------------------------------


class RelayStoreError(Exception):
    """Base class for relay-store failures."""


class RelayQuotaExceeded(RelayStoreError):
    """Raised when accepting a deposit would breach a quota."""


class RelayBadDeposit(RelayStoreError):
    """Raised when a deposit request is malformed or untrusted."""


# --- Public record ---------------------------------------------------------


@dataclass(frozen=True)
class StoredDeposit:
    """One relay-side record, ready for the recipient to fetch."""

    deposit_id: str
    recipient_public_id: str
    envelope: dict
    stored_at: int
    expires_at: int
    size_bytes: int


# --- Index record ----------------------------------------------------------


def _now() -> int:
    return int(time.time())


def _safe_recipient(recipient_public_id: str) -> str:
    """Filesystem-safe recipient id used for the per-recipient JSONL file."""
    safe = "".join(
        c if c.isalnum() or c in "._@+-" else "_" for c in recipient_public_id
    )
    return safe or "unknown"


# --- The store -------------------------------------------------------------


class RelayStore:
    """Encrypted, quota-bounded, TTL-aware relay store.

    Parameters
    ----------
    data_dir:
        Root directory. Subdirectory ``relay/`` is created on demand.
    master_key:
        32-byte secret that protects the at-rest encryption. Production
        code derives this from the node identity seed (see
        :func:`hmac_io_key`); tests can pass ``secrets.token_bytes(32)``.
    ttl_seconds:
        Default lifetime for a deposit.
    max_ttl_seconds:
        Hard ceiling on ``expires_at - stored_at``.
    max_deposits_per_recipient / max_bytes_per_recipient:
        Per-recipient caps.
    max_total_deposits / max_total_bytes:
        Global caps across every recipient.
    """

    def __init__(
        self,
        data_dir: Path,
        *,
        master_key: bytes,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_ttl_seconds: int = DEFAULT_MAX_TTL_SECONDS,
        max_deposits_per_recipient: int = DEFAULT_MAX_DEPOSITS_PER_RECIPIENT,
        max_bytes_per_recipient: int = DEFAULT_MAX_BYTES_PER_RECIPIENT,
        max_total_deposits: int = DEFAULT_MAX_TOTAL_DEPOSITS,
        max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
        hmac_key: Optional[bytes] = None,
    ) -> None:
        if not isinstance(master_key, (bytes, bytearray)) or len(master_key) < 32:
            raise RelayStoreError("master_key must be at least 32 bytes")
        if ttl_seconds <= 0 or ttl_seconds > max_ttl_seconds:
            raise RelayStoreError("ttl_seconds must be in (0, max_ttl_seconds]")
        self._master = bytes(master_key[:32])
        self._root = Path(str(data_dir)) / "relay"
        self._deposits_dir = self._root / "deposits"
        self._receipts_dir = self._root / "receipts"
        self._index_path = self._root / "index.json"
        self._tombstones_path = self._root / "index.tombstones.jsonl"
        self._ttl_seconds = int(ttl_seconds)
        self._max_ttl_seconds = int(max_ttl_seconds)
        self._max_deposits_per_recipient = int(max_deposits_per_recipient)
        self._max_bytes_per_recipient = int(max_bytes_per_recipient)
        self._max_total_deposits = int(max_total_deposits)
        self._max_total_bytes = int(max_total_bytes)
        self._lock = threading.RLock()
        # In-memory index: {deposit_id: {recipient, stored_at, expires_at, size}}
        self._index: dict[str, dict[str, Any]] = {}
        self._by_recipient: dict[str, set[str]] = {}
        self._total_size: int = 0
        # Counter of deposit ids issued in this process; used only for
        # monotonicity checks across restarts. We don't strictly need it
        # but it helps when debugging duplicate ids.
        self._issued = 0
        # HMAC key for the on-disk index; defaults to a derivation of
        # the master to forge index state.
        self._hmac_key = (
            hmac_key
            if hmac_key is not None
            else _hmac_io()[1](self._master)
        )
        self._root.mkdir(parents=True, exist_ok=True)
        self._deposits_dir.mkdir(parents=True, exist_ok=True)
        self._receipts_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        """Replay the on-disk index, applying tombstones if the snapshot
        fails HMAC verification."""
        snapshot: dict[str, dict[str, Any]] = {}
        if self._index_path.exists():
            try:
                _, _, read_json_protected, _ = _hmac_io()
                data = read_json_protected(self._index_path, self._hmac_key)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(k, str) and isinstance(v, dict):
                            snapshot[k] = v
            except Exception:
                snapshot = {}
        # Apply tombstone events on top of whatever we have. This is
        # how we recover if the snapshot file is rewritten: the
        # tombstone log is line-atomic and HMAC-protected, so an
        # attacker who rewrites the snapshot also has to rewrite
        # every tombstone since the last compaction.
        events = self._load_tombstones()
        merged = dict(snapshot)
        for ev in events:
            etype = ev.get("type")
            did = ev.get("deposit_id")
            if not isinstance(did, str):
                continue
            if etype == "deposit":
                rec = ev.get("record")
                if isinstance(rec, dict):
                    merged[did] = rec
            elif etype == "drop":
                merged.pop(did, None)
        # Rebuild the live counters from the merged state.
        self._index = merged
        self._by_recipient = {}
        self._total_size = 0
        for did, rec in self._index.items():
            if not self._record_is_valid(rec):
                continue
            if int(rec["expires_at"]) <= _now():
                # Expired; treat as gone for live counts. The file
                # still holds the body until the next sweep, but the
                # index entry is suppressed.
                continue
            recipient = str(rec["recipient_public_id"])
            self._by_recipient.setdefault(recipient, set()).add(did)
            self._total_size += int(rec["size_bytes"])

    def _load_tombstones(self) -> list[dict]:
        events: list[dict] = []
        path = self._tombstones_path
        # We never write the base ``path`` directly; each event lives
        # at ``<path>.<N>`` with a sidecar ``.hmac``. Skip the early
        # ``path.exists()`` check (which only fires if a stray file
        # was created) and probe the numbered files instead.

        import hashlib
        import hmac as _hmac
        n = 0
        while True:
            data_path = path.with_name(f"{path.name}.{n:08d}")
            tag_path = path.with_name(f"{path.name}.{n:08d}.hmac")

            if not data_path.exists():
                break
            if not tag_path.exists():
                n += 1
                continue
            try:
                body = data_path.read_bytes()
                tag = tag_path.read_text()
                expected = _hmac.new(self._hmac_key, body, hashlib.sha256).hexdigest()
                if not _hmac.compare_digest(tag, expected):
                    n += 1
                    continue
                ev = json.loads(body.decode("utf-8"))
                if isinstance(ev, dict):
                    events.append(ev)
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                pass
            n += 1
        return events

    def _append_tombstone(self, event: Mapping[str, Any]) -> None:
        seq = self._next_tombstone_seq()
        body = json.dumps(dict(event), separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
        import hashlib
        import hmac as _hmac

        tag = _hmac.new(self._hmac_key, body, hashlib.sha256).hexdigest()
        data_path = self._tombstones_path.with_name(
            f"{self._tombstones_path.name}.{seq:08d}"
        )
        tag_path = self._tombstones_path.with_name(
            f"{self._tombstones_path.name}.{seq:08d}.hmac"
        )
        data_path.write_bytes(body)
        tag_path.write_text(tag)

    def _next_tombstone_seq(self) -> int:
        n = 0
        while True:
            data_path = self._tombstones_path.with_name(
                f"{self._tombstones_path.name}.{n:08d}"
            )
            if not data_path.exists():
                return n
            n += 1

    def _save_index(self) -> None:
        if self._index_path.parent != self._root:
            self._index_path.parent.mkdir(parents=True, exist_ok=True)
        _, _, _, write_json_protected = _hmac_io()
        write_json_protected(self._index_path, self._index, self._hmac_key)

    @staticmethod
    def _record_is_valid(rec: Mapping[str, Any]) -> bool:
        try:
            return (
                isinstance(rec.get("recipient_public_id"), str)
                and isinstance(rec.get("envelope_path"), str)
                and isinstance(rec.get("nonce"), str)
                and isinstance(rec.get("aad_hash"), str)
                and int(rec.get("stored_at")) > 0
                and int(rec.get("expires_at")) > 0
                and int(rec.get("size_bytes")) > 0
            )
        except (TypeError, ValueError):
            return False

    # --- Crypto helpers -----------------------------------------------

    def _envelope_key(self, recipient_public_id: str) -> bytes:
        """Derive the per-recipient AEAD key."""
        import hashlib

        hkdf_salt = hashlib.sha256(
            recipient_public_id.encode("utf-8")
        ).digest()
        # Simple HKDF: HMAC-based with the recipient as salt.
        prk = hmac_sha256(self._master, hkdf_salt + _ENVELOPE_KEY_INFO)
        return hmac_sha256(prk, b"deposit-aead-key" + b"\x01")

    @staticmethod
    def _aad_for(recipient_public_id: str, deposit_id: str) -> bytes:
        # The AAD binds the ciphertext to (recipient, deposit_id) so a
        # relay cannot move a deposit between recipients or ids.
        return b"|".join(
            [
                recipient_public_id.encode("utf-8"),
                deposit_id.encode("utf-8"),
            ]
        )

    def _encrypt_envelope(
        self, recipient_public_id: str, deposit_id: str, envelope: Mapping[str, Any]
    ) -> tuple[str, str]:
        body = json.dumps(dict(envelope), separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
        if len(body) > _MAX_DEPOSIT_BYTES:
            raise RelayBadDeposit(
                f"envelope too large: {len(body)} > {_MAX_DEPOSIT_BYTES}"
            )
        aead = ChaCha20Poly1305(self._envelope_key(recipient_public_id))
        nonce = secrets.token_bytes(12)
        ct = aead.encrypt(nonce, body, self._aad_for(recipient_public_id, deposit_id))
        return (
            base64.b64encode(ct).decode("ascii"),
            base64.b64encode(nonce).decode("ascii"),
        )

    def _decrypt_envelope(
        self, recipient_public_id: str, deposit_id: str, ct_b64: str, nonce_b64: str
    ) -> dict:
        aead = ChaCha20Poly1305(self._envelope_key(recipient_public_id))
        try:
            ct = base64.b64decode(ct_b64)
            nonce = base64.b64decode(nonce_b64)
            body = aead.decrypt(
                nonce, ct, self._aad_for(recipient_public_id, deposit_id)
            )
        except Exception as exc:
            raise RelayStoreError(
                f"envelope decrypt failed: {type(exc).__name__}"
            ) from exc
        try:
            envelope = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RelayStoreError("envelope not valid JSON") from exc
        if not isinstance(envelope, dict):
            raise RelayStoreError("envelope must decode to a JSON object")
        return envelope

    # --- Deposit ------------------------------------------------------

    def deposit(
        self,
        *,
        sender_public_id: str,
        envelope: Mapping[str, Any],
        recipient_public_id: str,
        now: Optional[int] = None,
        ttl_seconds: Optional[int] = None,
    ) -> StoredDeposit:
        """Store ``envelope`` for ``recipient_public_id``.

        Idempotent on ``(recipient_public_id, message_id)``: a second
        deposit for the same pair returns the original record without
        counting against the quota.
        """
        if not isinstance(sender_public_id, str) or not sender_public_id:
            raise RelayBadDeposit("sender_public_id must be a non-empty string")
        if not _RECIPIENT_PATTERN.match(recipient_public_id):
            raise RelayBadDeposit("recipient_public_id is not a valid Narada id")
        if not isinstance(envelope, Mapping):
            raise RelayBadDeposit("envelope must be a JSON object")
        try:
            message_id = str(envelope["message_id"])
        except KeyError as exc:
            raise RelayBadDeposit("envelope missing message_id") from exc
        if not message_id:
            raise RelayBadDeposit("envelope has empty message_id")
        now_int = int(now) if now is not None else _now()
        ttl = int(ttl_seconds) if ttl_seconds is not None else self._ttl_seconds
        if ttl <= 0 or ttl > self._max_ttl_seconds:
            raise RelayBadDeposit(
                f"ttl_seconds out of range: {ttl} not in (0, {self._max_ttl_seconds}]"
            )
        expires_at = now_int + ttl
        with self._lock:
            # Idempotency: same (recipient, message_id) returns the
            # existing deposit if it is still live.
            for did, rec in self._index.items():
                if (
                    rec.get("recipient_public_id") == recipient_public_id
                    and rec.get("message_id") == message_id
                    and int(rec.get("expires_at", 0)) > now_int
                ):
                    stored = self._hydrate(did, rec)
                    if stored is not None:
                        return stored
            # Envelope body size (serialised) is what we charge against
            # the quota. We measure pre-encryption so the on-disk size
            # matches what the user can audit later.
            body = json.dumps(
                dict(envelope), separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
            size_bytes = len(body)
            if size_bytes > self._max_bytes_per_recipient:
                raise RelayQuotaExceeded(
                    f"deposit size {size_bytes} exceeds per-recipient cap"
                )
            existing_ids = self._by_recipient.get(recipient_public_id, set())
            live_existing = {
                did
                for did in existing_ids
                if int(self._index[did]["expires_at"]) > now_int
            }
            if len(live_existing) >= self._max_deposits_per_recipient:
                raise RelayQuotaExceeded(
                    f"recipient already at deposit cap "
                    f"({self._max_deposits_per_recipient})"
                )
            existing_bytes = sum(
                int(self._index[did]["size_bytes"])
                for did in live_existing
            )
            if existing_bytes + size_bytes > self._max_bytes_per_recipient:
                raise RelayQuotaExceeded(
                    f"recipient already at byte cap "
                    f"({existing_bytes}+{size_bytes} > "
                    f"{self._max_bytes_per_recipient})"
                )
            live_total = sum(
                1
                for did, rec in self._index.items()
                if int(rec.get("expires_at", 0)) > now_int
            )
            live_total_bytes = sum(
                int(rec["size_bytes"])
                for rec in self._index.values()
                if int(rec.get("expires_at", 0)) > now_int
            )
            if live_total >= self._max_total_deposits:
                raise RelayQuotaExceeded(
                    f"relay at deposit cap ({self._max_total_deposits})"
                )
            if live_total_bytes + size_bytes > self._max_total_bytes:
                raise RelayQuotaExceeded(
                    f"relay at byte cap "
                    f"({live_total_bytes}+{size_bytes} > "
                    f"{self._max_total_bytes})"
                )
            deposit_id = str(uuid.uuid4())
            ct_b64, nonce_b64 = self._encrypt_envelope(
                recipient_public_id, deposit_id, envelope
            )
            envelope_path = self._write_deposit_blob(deposit_id, ct_b64, nonce_b64)
            aad_hash_b64 = base64.b64encode(
                self._aad_for(recipient_public_id, deposit_id)
            ).decode("ascii")
            record = {
                "recipient_public_id": recipient_public_id,
                "message_id": message_id,
                "sender_public_id": sender_public_id,
                "envelope_path": envelope_path,
                "nonce": nonce_b64,
                "aad_hash": aad_hash_b64,
                "stored_at": now_int,
                "expires_at": expires_at,
                "size_bytes": size_bytes,
            }
            self._index[deposit_id] = record
            self._by_recipient.setdefault(recipient_public_id, set()).add(deposit_id)
            self._total_size += size_bytes
            self._append_tombstone({"type": "deposit", "deposit_id": deposit_id, "record": record})
            self._save_index()
            self._issued += 1
            return StoredDeposit(
                deposit_id=deposit_id,
                recipient_public_id=recipient_public_id,
                envelope=dict(envelope),
                stored_at=now_int,
                expires_at=expires_at,
                size_bytes=size_bytes,
            )

    def _write_deposit_blob(
        self, deposit_id: str, ct_b64: str, nonce_b64: str
    ) -> str:
        safe = _safe_recipient(deposit_id)
        path = self._deposits_dir / f"{safe}.jsonl"
        line = json.dumps(
            {"id": deposit_id, "ct": ct_b64, "nonce": nonce_b64},
            separators=(",", ":"),
            sort_keys=True,
        )
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=str(self._deposits_dir),
            prefix=safe + ".",
            suffix=".tmp",
            delete=False,
        ) as f:
            tmp_name = f.name
            f.write((line + "\n").encode("utf-8"))
        os.replace(tmp_name, str(path))
        return str(path)

    # --- Fetch --------------------------------------------------------

    def fetch(
        self,
        *,
        recipient_public_id: str,
        limit: int = 64,
        now: Optional[int] = None,
    ) -> list[StoredDeposit]:
        if not isinstance(recipient_public_id, str):
            raise RelayBadDeposit("recipient_public_id must be a string")
        if limit <= 0:
            return []
        now_int = int(now) if now is not None else _now()
        with self._lock:
            ids = list(self._by_recipient.get(recipient_public_id, ()))
            out: list[StoredDeposit] = []
            for did in sorted(ids):
                rec = self._index.get(did)
                if rec is None:
                    continue
                if int(rec.get("expires_at", 0)) <= now_int:
                    continue
                hydrated = self._hydrate(did, rec)
                if hydrated is None:
                    continue
                out.append(hydrated)
                if len(out) >= limit:
                    break
            return out

    def _hydrate(
        self, deposit_id: str, record: Mapping[str, Any]
    ) -> Optional[StoredDeposit]:
        envelope_path = record.get("envelope_path")
        if not isinstance(envelope_path, str):
            return None
        path = Path(envelope_path)
        if not path.exists():
            return None
        try:
            line = path.read_text(encoding="utf-8").strip()
            blob = json.loads(line)
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(blob, dict):
            return None
        ct_b64 = blob.get("ct")
        nonce_b64 = blob.get("nonce")
        if not isinstance(ct_b64, str) or not isinstance(nonce_b64, str):
            return None
        try:
            envelope = self._decrypt_envelope(
                str(record["recipient_public_id"]),
                deposit_id,
                ct_b64,
                nonce_b64,
            )
        except RelayStoreError:
            return None
        return StoredDeposit(
            deposit_id=deposit_id,
            recipient_public_id=str(record["recipient_public_id"]),
            envelope=envelope,
            stored_at=int(record["stored_at"]),
            expires_at=int(record["expires_at"]),
            size_bytes=int(record["size_bytes"]),
        )

    # --- Drop ---------------------------------------------------------

    def drop(
        self,
        *,
        recipient_public_id: str,
        deposit_ids: Iterable[str],
        now: Optional[int] = None,
    ) -> int:
        """Remove deposits by id. Only the owning recipient can drop them.

        Returns the number of deposits actually removed.
        """
        ids = list(deposit_ids)
        if not ids:
            return 0
        now_int = int(now) if now is not None else _now()
        removed = 0
        with self._lock:
            for did in ids:
                rec = self._index.get(did)
                if rec is None:
                    continue
                if rec.get("recipient_public_id") != recipient_public_id:
                    continue
                if int(rec.get("expires_at", 0)) <= now_int:
                    # Already expired: still remove the index entry to
                    # bound the size of the live set.
                    pass
                self._by_recipient.get(recipient_public_id, set()).discard(did)
                size = int(rec.get("size_bytes", 0))
                self._index.pop(did, None)
                self._total_size = max(0, self._total_size - size)
                # Remove the on-disk blob. Missing files are not a
                # failure: the index is the source of truth.
                path = Path(rec.get("envelope_path", ""))
                try:
                    if path.exists():
                        path.unlink()
                except OSError:
                    pass
                self._append_tombstone(
                    {"type": "drop", "deposit_id": did}
                )
                removed += 1
            if removed:
                self._save_index()
            return removed

    # --- Sweep --------------------------------------------------------

    def sweep(self, *, now: Optional[int] = None) -> int:
        """Reap expired entries. Returns the number removed."""
        now_int = int(now) if now is not None else _now()
        with self._lock:
            expired_ids = [
                did
                for did, rec in self._index.items()
                if int(rec.get("expires_at", 0)) <= now_int
            ]
            if not expired_ids:
                return 0
            for did in expired_ids:
                rec = self._index.pop(did, None)
                if rec is None:
                    continue
                recipient = str(rec.get("recipient_public_id", ""))
                self._by_recipient.get(recipient, set()).discard(did)
                self._total_size = max(
                    0, self._total_size - int(rec.get("size_bytes", 0))
                )
                path = Path(rec.get("envelope_path", ""))
                try:
                    if path.exists():
                        path.unlink()
                except OSError:
                    pass
                self._append_tombstone(
                    {"type": "drop", "deposit_id": did}
                )
            self._save_index()
            return len(expired_ids)

    # --- Stats --------------------------------------------------------

    def stats(self) -> dict:
        with self._lock:
            live_count = len(self._index)
            live_bytes = self._total_size
            return {
                "live_deposits": live_count,
                "live_bytes": live_bytes,
                "recipients": len(self._by_recipient),
                "issued_total": self._issued,
            }


# --- HMAC helper -----------------------------------------------------------


def hmac_sha256(key: bytes, data: bytes) -> bytes:
    import hashlib
    import hmac

    return hmac.new(key, data, hashlib.sha256).digest()


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "DEFAULT_MAX_TTL_SECONDS",
    "DEFAULT_MAX_DEPOSITS_PER_RECIPIENT",
    "DEFAULT_MAX_BYTES_PER_RECIPIENT",
    "DEFAULT_MAX_TOTAL_DEPOSITS",
    "DEFAULT_MAX_TOTAL_BYTES",
    "RelayStore",
    "RelayStoreError",
    "RelayQuotaExceeded",
    "RelayBadDeposit",
    "StoredDeposit",
]
