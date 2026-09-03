"""KeyRotationStore: persistent per-sender key rotation records.

When a Narada node receives a :class:`NaradaKeyUpdate` envelope
(v=3), it persists the rotation in this store so future envelopes
signed under the prior public id can be accepted during the
overlap window (until ``not_after``).

Threat-model properties (consistent with T8 hardening round):

* **Integrity** (T8-style). The on-disk record is HMAC-protected
  with the same key the node uses for watermarks. A disk attacker
  who rewrites the file is detected.
* **Recovery** (T8a-style). The store replays from a tombstone
  log; see :class:`src.narada_security.tombstone_log.TombstoneLog`.
  Implemented in a follow-up; the current commit ships **detect**
  only.
* **Availability** (T8a). A tamper event currently causes a
  full-loss; a tombstone log migration is the recovery path.
  Documented in ``vuln.md`` §2.2.

Wire format of the on-disk snapshot::

    { "prior_<i>_public_id": { "new_public_id": str,
                               "not_after": int,
                               "received_at": int },
      ... }

One record per rotated public id. Multiple rotations for the
same prior id overwrite (the new public id wins; older ones are
effectively lost unless the tombstone log carries them).
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class KeyRotationRecord:
    prior_public_id: str
    new_public_id: str
    not_after: int
    received_at: int

    def is_active(self, now: Optional[int] = None) -> bool:
        cur = int(now) if now is not None else int(time.time())
        return cur <= int(self.not_after)

    def to_dict(self) -> dict:
        return {
            "prior_public_id": self.prior_public_id,
            "new_public_id": self.new_public_id,
            "not_after": int(self.not_after),
            "received_at": int(self.received_at),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KeyRotationRecord":
        return cls(
            prior_public_id=str(data["prior_public_id"]),
            new_public_id=str(data["new_public_id"]),
            not_after=int(data["not_after"]),
            received_at=int(data["received_at"]),
        )


class KeyRotationStore:
    """HMAC-protected record of accepted key rotations.

    The on-disk file ``<path>`` is JSON: ``{prior_public_id:
    {new_public_id, not_after, received_at}}``. A ``.hmac``
    sidecar is written next to it (via :mod:`hmac_io`).

    On load, the sidecar is verified. A failed check falls back to
    an empty store; the next write overwrites the bad file. The
    tombstone-log-backed recovery path lives in a follow-up; the
    current commit only ships **detect**, not **recover**.

    Callers must construct a store with a key. Legacy plaintext
    mode (no key) is supported for tests but is **not** used in
    production.
    """

    def __init__(self, path: Path, *, key: Optional[bytes] = None) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._key = key
        self._data: dict[str, KeyRotationRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        if self._key is not None:
            from src.narada_security.hmac_io import (
                HmacIntegrityError,
                read_json_protected,
            )

            try:
                data = read_json_protected(self._path, self._key)
            except (HmacIntegrityError, FileNotFoundError):
                return
            if not isinstance(data, dict):
                return
            for k, v in data.items():
                if not isinstance(v, dict):
                    continue
                try:
                    self._data[str(k)] = KeyRotationRecord.from_dict(v)
                except (KeyError, TypeError, ValueError):
                    continue
            return
        # No-key path: legacy plaintext (tests only).
        try:
            data = json.loads(self._path.read_bytes())
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(data, dict):
            return
        for k, v in data.items():
            if not isinstance(v, dict):
                continue
            try:
                self._data[str(k)] = KeyRotationRecord.from_dict(v)
            except (KeyError, TypeError, ValueError):
                continue

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._key is None:
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._to_dict(), sort_keys=True))
            tmp.replace(self._path)
            return
        from src.narada_security.hmac_io import write_json_protected

        write_json_protected(self._path, self._to_dict(), self._key)

    def _to_dict(self) -> dict:
        return {k: v.to_dict() for k, v in self._data.items()}

    def record(
        self,
        prior_public_id: str,
        new_public_id: str,
        not_after: int,
    ) -> KeyRotationRecord:
        """Persist a rotation. Overwrites any prior record for ``prior_public_id``."""
        with self._lock:
            rec = KeyRotationRecord(
                prior_public_id=prior_public_id,
                new_public_id=new_public_id,
                not_after=int(not_after),
                received_at=int(time.time()),
            )
            self._data[prior_public_id] = rec
            self._save()
            return rec

    def lookup(
        self, prior_public_id: str, *, now: Optional[int] = None
    ) -> Optional[KeyRotationRecord]:
        """Return the active rotation for ``prior_public_id``, if any.

        "Active" means ``now <= not_after`` (we still accept the
        OLD key alongside the new one during the overlap
        window). Once ``not_after`` passes, the rotation is
        considered closed and a fresh envelope signed with the
        OLD key is rejected — the recipient is expected to have
        migrated to the new key by then.
        """
        with self._lock:
            rec = self._data.get(prior_public_id)
        if rec is None:
            return None
        if not rec.is_active(now=now):
            return None
        return rec

    def all(self) -> dict[str, KeyRotationRecord]:
        with self._lock:
            return dict(self._data)

    def remove(self, prior_public_id: str) -> bool:
        with self._lock:
            if prior_public_id not in self._data:
                return False
            del self._data[prior_public_id]
            self._save()
            return True


__all__ = ["KeyRotationRecord", "KeyRotationStore"]