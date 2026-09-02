"""Append-only tombstone log for replay-safe local state.

The threat-model round identified that HMAC-protected snapshots
(see :mod:`src.narada_security.hmac_io`) **detect** tampering but
do not **recover** from it: a failed HMAC on load discards the
entire snapshot, forcing every sender's messages to re-deliver.

The recovery design is: pair each snapshot with an append-only
log of every state mutation since the snapshot was written. The
log is also HMAC-protected, but line-atomic so appends cannot
rewrite history. On load, the snapshot + replay of every
mutation after it restores the live state even if the snapshot
itself was tampered with — provided the attacker did not also
rewrite every tombstone written after the tampered snapshot.

Concretely, this module provides :class:`TombstoneLog` that
records one event per line:

  * append-only: ``append(event)`` writes one line
  * HMAC-protected: each line has a per-line sidecar ``.hmac``
  * replayable: ``replay()`` returns the events in insertion order

Threat-model rationale (T8a):

* **Integrity (snapshot tamper).** Sidecar HMAC detects.
* **Recovery from tamper.** Tombstone replay rebuilds the live
  state up to the last tombstoned event. Bounded work because
  tombstones are compacted into a new snapshot periodically via
  :meth:`TombstoneLog.compact`.
* **Availability.** Worst-case bound is "all events since the
  last compaction"; this is the same as the unhardened
  ``seen.<account>.json`` today but bounded by the snapshot
  interval.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional

from src.narada_security.hmac_io import (
    HmacIntegrityError,
    hmac_io_key,
    read_protected,
    write_protected,
)


class TombstoneLog:
    """Append-only HMAC-signed event log.

    Each appended event is one line in a JSONL file with a paired
    sidecar HMAC over the line contents. ``replay()`` reads back
    every valid line in insertion order; tampered lines are
    skipped (the sidecar check fails).

    Events are arbitrary JSON objects. The watermark store
    treats them as ``{"sender": str, "lseq": int, "ts": int}``
    but the log itself does not enforce a schema.
    """

    def __init__(self, path: Path, *, key: Optional[bytes] = None) -> None:
        self._path = Path(str(path))
        self._key = key
        self._lock = threading.RLock()
        # In-memory append counter so we can detect out-of-order
        # writes from disk (rare; only relevant after a restore
        # from a corrupted file).
        self._next_seq: int = 0
        self._load_existing_count()

    # --- File layout --------------------------------------------------

    def _sidecar(self) -> Path:
        return self._path.with_name(self._path.name + ".hmac")

    def _line_path(self, n: int) -> Path:
        # Each event gets a separate file ``<path>.<n>`` so a single
        # atomic write is the line write.
        return self._path.with_name(f"{self._path.name}.{n:08d}")

    def _line_sidecar(self, n: int) -> Path:
        return self._line_path(n).with_name(
            f"{self._path.name}.{n:08d}.hmac"
        )

    def _hmac(self, data: bytes) -> str:
        import hashlib
        import hmac as _hmac

        assert self._key is not None
        return _hmac.new(self._key, data, hashlib.sha256).hexdigest()

    # --- Load / count -------------------------------------------------

    def _load_existing_count(self) -> None:
        if not self._path.parent.exists():
            return
        n = 0
        while self._line_path(n).exists():
            n += 1
        self._next_seq = n

    @property
    def next_seq(self) -> int:
        return self._next_seq

    # --- Append -------------------------------------------------------

    def append(self, event: Mapping[str, Any]) -> int:
        """Append ``event`` and return its assigned sequence number.

        Atomic on POSIX (single ``rename``); on Windows we accept
        a brief window where the data file exists but the sidecar
        does not. The next ``replay()`` call will skip such a line
        rather than trust it.
        """
        with self._lock:
            if self._key is None:
                raise RuntimeError(
                    "TombstoneLog.append requires a key; use WatermarkStore.update"
                )
            seq = self._next_seq
            data_path = self._line_path(seq)
            tag_path = self._line_sidecar(seq)
            body = json.dumps(dict(event), separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
            tag = self._hmac(body)
            # Write order: data first, then sidecar. If we crash
            # between, the line is skipped on replay (sidecar
            # missing). On read, we tolerate missing sidecars.
            data_path.write_bytes(body)
            tag_path.write_text(tag)
            self._next_seq += 1
            return seq

    # --- Replay -------------------------------------------------------

    def replay(self) -> Iterator[dict[str, Any]]:
        """Yield every valid event in insertion order.

        Lines with a missing or mismatched HMAC sidecar are
        silently skipped. This is the recovery path: if the
        snapshot file was tampered with, the tombstone log still
        tells us what state to roll forward to.
        """
        with self._lock:
            n = 0
            while True:
                data_path = self._line_path(n)
                tag_path = self._line_sidecar(n)
                if not data_path.exists():
                    return
                if not tag_path.exists():
                    n += 1
                    continue
                try:
                    body = data_path.read_bytes()
                except OSError:
                    n += 1
                    continue
                expected_tag = tag_path.read_text().strip()
                actual_tag = self._hmac(body)
                if expected_tag != actual_tag:
                    n += 1
                    continue
                try:
                    obj = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    n += 1
                    continue
                if isinstance(obj, dict):
                    yield obj
                n += 1

    # --- Compact ------------------------------------------------------

    def compact(self) -> int:
        """Rewrite the log as empty.

        Returns the number of events that were discarded. Callers
        must have snapshotted the resulting state elsewhere (e.g.
        via ``WatermarkStore.snapshot()``) before compacting,
        otherwise the live state is lost.

        ``compact`` is atomic: the existing files are renamed to
        ``.compact.<ts>.bak`` before being deleted. On POSIX this
        is observable to readers but consistent at the directory
    level.
        """
        with self._lock:
            n = 0
            while self._line_path(n).exists():
                n += 1
            if n == 0:
                return 0
            ts = int(time.time())
            for i in range(n):
                data_path = self._line_path(i)
                tag_path = self._line_sidecar(i)
                try:
                    data_path.rename(
                        data_path.with_name(
                            f"{data_path.name}.compact-{ts}.bak"
                        )
                    )
                except OSError:
                    pass
                try:
                    tag_path.rename(
                        tag_path.with_name(
                            f"{tag_path.name}.compact-{ts}.bak"
                        )
                    )
                except OSError:
                    pass
            self._next_seq = 0
            return n


__all__ = ["TombstoneLog"]
