"""Identity mapping for the Narada gateway (Phase 5).

The mapping file is a JSON document with two top-level keys:

* ``narada_to_smtp``: maps a Narada public id (``narada1...``) to
  a conventional email address.
* ``smtp_to_narada``: maps a conventional email address to a
  Narada public id.

A mapping must exist on the path being used; missing mappings
are refused via :class:`NoMappingError`.

The mapping is intentionally simple — a single JSON file, loaded
on startup, reloaded on demand. A future phase can replace this
with a directory or signed mapping registry.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Iterable, Optional

from .errors import NoMappingError


# Bech32m narada1 ids. Same charset we use elsewhere.
_NARADA_PATTERN = re.compile(r"^[a-z0-9]{6,16}1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]+$")
# Conventional email — local@domain. The local part is
# deliberately permissive (RFC 5321 allows a lot); the domain
# part is the more constrained identifier.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class IdentityMapping:
    """In-memory identity mapping for the gateway.

    The mapping is loaded from a JSON file and held behind a lock
    so a reload from another thread does not race with a lookup.
    """

    def __init__(
        self,
        *,
        narada_to_smtp: Optional[dict[str, str]] = None,
        smtp_to_narada: Optional[dict[str, str]] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._narada_to_smtp: dict[str, str] = {}
        self._smtp_to_narada: dict[str, str] = {}
        if narada_to_smtp:
            self.set_narada_to_smtp(narada_to_smtp)
        if smtp_to_narada:
            self.set_smtp_to_narada(smtp_to_narada)

    # --- Load / save --------------------------------------------------

    @classmethod
    def from_file(cls, path: Path) -> "IdentityMapping":
        data = json.loads(Path(path).read_bytes())
        if not isinstance(data, dict):
            raise ValueError("mapping file must be a JSON object")
        narada_to_smtp = data.get("narada_to_smtp") or {}
        smtp_to_narada = data.get("smtp_to_narada") or {}
        if not isinstance(narada_to_smtp, dict):
            raise ValueError("narada_to_smtp must be an object")
        if not isinstance(smtp_to_narada, dict):
            raise ValueError("smtp_to_narada must be an object")
        return cls(
            narada_to_smtp={str(k): str(v) for k, v in narada_to_smtp.items()},
            smtp_to_narada={str(k): str(v) for k, v in smtp_to_narada.items()},
        )

    def save(self, path: Path) -> None:
        with self._lock:
            payload = {
                "narada_to_smtp": dict(self._narada_to_smtp),
                "smtp_to_narada": dict(self._smtp_to_narada),
            }
        Path(path).write_bytes(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )

    def reload_from_file(self, path: Path) -> None:
        fresh = IdentityMapping.from_file(path)
        with self._lock:
            self._narada_to_smtp = dict(fresh._narada_to_smtp)
            self._smtp_to_narada = dict(fresh._smtp_to_narada)

    # --- Mutators -----------------------------------------------------

    def set_narada_to_smtp(self, mapping: dict[str, str]) -> None:
        clean = {str(k): str(v) for k, v in mapping.items()}
        for k, v in clean.items():
            _validate_narada(k)
            _validate_email(v)
        with self._lock:
            self._narada_to_smtp = clean

    def set_smtp_to_narada(self, mapping: dict[str, str]) -> None:
        clean = {str(k): str(v) for k, v in mapping.items()}
        for k, v in clean.items():
            _validate_email(k)
            _validate_narada(v)
        with self._lock:
            self._smtp_to_narada = clean

    # --- Lookups ------------------------------------------------------

    def lookup_narada_to_smtp(self, narada_id: str) -> str:
        """Return the conventional address for a Narada id, or
        raise :class:`NoMappingError`."""
        if not isinstance(narada_id, str):
            raise NoMappingError("narada_id must be a string")
        with self._lock:
            value = self._narada_to_smtp.get(narada_id)
        if value is None:
            raise NoMappingError(
                f"no SMTP mapping for Narada id {narada_id!r}"
            )
        return value

    def lookup_smtp_to_narada(self, email_addr: str) -> str:
        """Return the Narada id for a conventional address, or
        raise :class:`NoMappingError`."""
        if not isinstance(email_addr, str):
            raise NoMappingError("email_addr must be a string")
        with self._lock:
            value = self._smtp_to_narada.get(email_addr.lower())
        if value is None:
            raise NoMappingError(
                f"no Narada mapping for SMTP address {email_addr!r}"
            )
        return value

    def try_lookup_smtp_to_narada(self, email_addr: str) -> Optional[str]:
        """Non-raising variant of :meth:`lookup_smtp_to_narada`."""
        if not isinstance(email_addr, str):
            return None
        with self._lock:
            return self._smtp_to_narada.get(email_addr.lower())

    def try_lookup_narada_to_smtp(self, narada_id: str) -> Optional[str]:
        """Non-raising variant of :meth:`lookup_narada_to_smtp`."""
        if not isinstance(narada_id, str):
            return None
        with self._lock:
            return self._narada_to_smtp.get(narada_id)

    # --- Introspection ------------------------------------------------

    def narada_ids(self) -> Iterable[str]:
        with self._lock:
            return list(self._narada_to_smtp.keys())

    def smtp_addresses(self) -> Iterable[str]:
        with self._lock:
            return list(self._smtp_to_narada.keys())


def _validate_narada(value: str) -> None:
    if not _NARADA_PATTERN.match(value):
        raise ValueError(f"not a Narada public id: {value!r}")


def _validate_email(value: str) -> None:
    if not _EMAIL_PATTERN.match(value):
        raise ValueError(f"not an email address: {value!r}")


__all__ = ["IdentityMapping"]
