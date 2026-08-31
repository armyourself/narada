"""Persistent outbox for Lattice messages (Phase 2 MVP).

When the recipient is offline, the sender's node queues the envelope
on disk and retries with exponential backoff: 1m, 5m, 30m, 2h, 12h.
After 12h of failed attempts the entry moves to a "dead letter"
file so the user can inspect it without polluting the active queue.

Storage layout (one JSON line per pending message, atomic writes)::

    <data_dir>/outbox/<account_id>.jsonl
    <data_dir>/outbox/dead-letter/<account_id>.jsonl

Each line::

    {
      "message_id": "...",
      "account_id": "alice@example.com",
      "recipient_public_id": "lattice1...",
      "envelope": {...as built by LatticeEnvelope.as_dict()...},
      "next_attempt_at": 1735689700,
      "attempt_count": 0,
      "last_error": null
    }
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping, Optional


_BACKOFF_SCHEDULE_SECONDS = (60, 300, 1800, 7200, 43200)  # 1m, 5m, 30m, 2h, 12h
_MAX_ATTEMPTS = len(_BACKOFF_SCHEDULE_SECONDS)


@dataclass
class OutboxEntry:
    """One queued envelope waiting for delivery."""

    message_id: str
    account_id: str
    recipient_public_id: str
    envelope: dict[str, Any]
    next_attempt_at: int
    attempt_count: int = 0
    last_error: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "OutboxEntry":
        data = json.loads(line)
        return cls(
            message_id=str(data["message_id"]),
            account_id=str(data["account_id"]),
            recipient_public_id=str(data["recipient_public_id"]),
            envelope=dict(data["envelope"]),
            next_attempt_at=int(data["next_attempt_at"]),
            attempt_count=int(data.get("attempt_count", 0) or 0),
            last_error=data.get("last_error"),
        )

    def next_delay_seconds(self) -> int:
        """Return the delay (seconds) before the next attempt.

        Indexes the schedule with ``attempt_count - 1`` so that:
        - after 1 failure (attempt_count=1) the next delay is the
          smallest (60s),
        - after 2 failures (attempt_count=2) the next delay is 300s,
        - etc.
        """
        idx = max(0, min(self.attempt_count - 1, len(_BACKOFF_SCHEDULE_SECONDS) - 1))
        return _BACKOFF_SCHEDULE_SECONDS[idx]


class Outbox:
    """JSONL-backed per-account outbox with exponential-backoff retry.

    Thread-safe. Persistence is line-atomic: writes go to a tmp file
    and are renamed into place, so a process crash mid-write cannot
    leave a half-finished line in the file.
    """

    def __init__(
        self,
        data_dir: Path,
        *,
        now_fn=time.time,
    ) -> None:
        self._outbox_dir = Path(str(data_dir)) / "outbox"
        self._dead_letter_dir = self._outbox_dir / "dead-letter"
        self._outbox_dir.mkdir(parents=True, exist_ok=True)
        self._dead_letter_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._now_fn = now_fn

    def _path_for(self, account_id: str, dead: bool = False) -> Path:
        directory = self._dead_letter_dir if dead else self._outbox_dir
        return directory / f"{_safe_account_id(account_id)}.jsonl"

    def enqueue(
        self,
        *,
        account_id: str,
        recipient_public_id: str,
        envelope: Mapping[str, Any],
        first_attempt_delay_seconds: int = 0,
    ) -> OutboxEntry:
        """Append a new pending envelope to the account's queue."""
        message_id = str(envelope["message_id"])
        entry = OutboxEntry(
            message_id=message_id,
            account_id=account_id,
            recipient_public_id=recipient_public_id,
            envelope=dict(envelope),
            next_attempt_at=int(self._now_fn()) + first_attempt_delay_seconds,
            attempt_count=0,
            last_error=None,
        )
        with self._lock:
            self._append_line(self._path_for(account_id), entry)
        return entry

    def list_due(self, account_id: str) -> list[OutboxEntry]:
        """Return entries for ``account_id`` that are due for an attempt."""
        now = int(self._now_fn())
        return [
            e for e in self._read_all(account_id)
            if e.next_attempt_at <= now
        ]

    def list_all(self, account_id: str) -> list[OutboxEntry]:
        return self._read_all(account_id)

    def list_all_accounts(self) -> list[str]:
        """Return all account_ids that have a non-empty queue file."""
        accounts: list[str] = []
        for path in self._outbox_dir.glob("*.jsonl"):
            aid = path.stem
            if path.stat().st_size > 0:
                accounts.append(aid)
        return accounts

    def mark_delivered(self, account_id: str, message_id: str) -> bool:
        """Remove an entry after a successful send. Returns True if it was found."""
        with self._lock:
            entries = self._read_all(account_id)
            kept = [e for e in entries if e.message_id != message_id]
            if len(kept) == len(entries):
                return False
            self._rewrite(self._path_for(account_id), kept)
            return True

    def mark_failed(
        self,
        account_id: str,
        message_id: str,
        error: str,
        *,
        dead_letter: bool = False,
    ) -> Optional[OutboxEntry]:
        """Increment attempt count, record error, and reschedule or move to dead-letter.

        Returns the updated entry, or None if the message_id was not
        in the queue.

        Backoff: the schedule is indexed by the attempt count *after*
        the increment. So the first failure (attempt_count 0 -> 1) uses
        the 60s delay, the second (1 -> 2) uses 300s, etc.
        """
        with self._lock:
            entries = self._read_all(account_id)
            for i, e in enumerate(entries):
                if e.message_id != message_id:
                    continue
                next_count = e.attempt_count + 1
                e.last_error = error
                if dead_letter or next_count >= _MAX_ATTEMPTS:
                    self._rewrite(self._path_for(account_id), entries[:i] + entries[i + 1 :])
                    e.attempt_count = next_count
                    self._append_line(self._path_for(account_id, dead=True), e)
                    return e
                e.attempt_count = next_count
                e.next_attempt_at = int(self._now_fn()) + e.next_delay_seconds()
                self._rewrite(self._path_for(account_id), entries)
                return e
            return None

    def remove(self, account_id: str, message_id: str) -> bool:
        """Remove an entry unconditionally (e.g. user cancels the send)."""
        with self._lock:
            entries = self._read_all(account_id)
            kept = [e for e in entries if e.message_id != message_id]
            if len(kept) == len(entries):
                return False
            self._rewrite(self._path_for(account_id), kept)
            return True

    def _read_all(self, account_id: str) -> list[OutboxEntry]:
        path = self._path_for(account_id)
        if not path.exists():
            return []
        out: list[OutboxEntry] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(OutboxEntry.from_json(line))
                except (json.JSONDecodeError, KeyError, ValueError):
                    # Skip corrupt lines; they will not be retried.
                    continue
        return out

    def _append_line(self, path: Path, entry: OutboxEntry) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = entry.to_json() + "\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(line)

    def _rewrite(self, path: Path, entries: list[OutboxEntry]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not entries:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix=path.name, suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                for e in entries:
                    f.write(e.to_json() + "\n")
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


def _safe_account_id(account_id: str) -> str:
    """Filesystem-safe filename derived from ``account_id``.

    The full validation happens at the router; this is just a defense
    against the outbox being called with a path-traversal-shaped id.
    """
    safe = "".join(c if c.isalnum() or c in "._@+-" else "_" for c in account_id)
    return safe or "unknown"


__all__ = [
    "Outbox",
    "OutboxEntry",
]
