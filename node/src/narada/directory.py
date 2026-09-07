"""Narada directory (Phase 2 MVP).

A :class:`NaradaDirectory` maps a recipient's ``narada1...`` public
id to a base URL where the recipient's node accepts envelopes (the
``/Narada/inbox`` endpoint). Today the only implementation is
:class:`LocalContactList`, a JSON-backed file under the node data
directory. Phase 3+ will add a real distributed directory.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


_ACCOUNT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._@+\-]{1,254}$")


def _validate_account_id(account_id: str) -> None:
    if not isinstance(account_id, str) or not _ACCOUNT_ID_PATTERN.match(account_id):
        raise ValueError(
            "account_id must be 1-254 chars of letters, digits, '.', '_', "
            "'-', '@' or '+'"
        )


def _validate_url(url: str) -> None:
    if not isinstance(url, str) or not url.startswith(
        ("http://", "https://", "mem://")
    ):
        raise ValueError("base url must start with http://, https://, or mem://")
class NaradaDirectory(ABC):
    """Abstract directory of recipient -> base_url mappings."""

    @abstractmethod
    def lookup(self, public_id: str) -> Optional[str]:
        """Return the base URL for ``public_id`` or None if not known."""

    @abstractmethod
    def add(self, public_id: str, base_url: str, account_id: str) -> None:
        """Add (or update) an entry.

        ``account_id`` is the local account the user uses for this
        contact; it is what the outbox keys its per-account queue by.
        """

    @abstractmethod
    def remove(self, public_id: str) -> bool:
        """Remove an entry. Returns True if it existed."""

    @abstractmethod
    def all_entries(self) -> list[tuple[str, str, str]]:
        """Return all ``(public_id, base_url, account_id)`` tuples."""


class LocalContactList(NaradaDirectory):
    """JSON-backed contact list, one file per node.

    File format::

        {
          "version": 1,
          "contacts": [
            {"public_id": "narada1...", "base_url": "http://127.0.0.1:8123",
             "account_id": "bob@example.com"},
            ...
          ]
        }
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._contacts: dict[str, dict[str, str]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        contacts = data.get("contacts", []) if isinstance(data, dict) else []
        for entry in contacts:
            if not isinstance(entry, dict):
                continue
            pid = entry.get("public_id")
            url = entry.get("base_url")
            aid = entry.get("account_id")
            if not isinstance(pid, str) or not isinstance(url, str) or not isinstance(aid, str):
                continue
            try:
                _validate_account_id(aid)
                _validate_url(url)
            except ValueError:
                continue
            self._contacts[pid] = {"public_id": pid, "base_url": url, "account_id": aid}

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "contacts": list(self._contacts.values())}
        # Atomic write: tmp file + rename.
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix=self._path.name, suffix=".tmp", dir=self._path.parent
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
            os.replace(tmp_path, self._path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def lookup(self, public_id: str) -> Optional[str]:
        with self._lock:
            entry = self._contacts.get(public_id)
            return entry["base_url"] if entry else None

    def add(self, public_id: str, base_url: str, account_id: str) -> None:
        if not isinstance(public_id, str) or not public_id:
            raise ValueError("public_id must be a non-empty string")
        _validate_url(base_url)
        _validate_account_id(account_id)
        with self._lock:
            self._contacts[public_id] = {
                "public_id": public_id,
                "base_url": base_url,
                "account_id": account_id,
            }
            self._persist()

    def remove(self, public_id: str) -> bool:
        with self._lock:
            if public_id in self._contacts:
                del self._contacts[public_id]
                self._persist()
                return True
            return False

    def all_entries(self) -> list[tuple[str, str, str]]:
        with self._lock:
            return [
                (e["public_id"], e["base_url"], e["account_id"])
                for e in self._contacts.values()
            ]


class InMemoryDirectory(NaradaDirectory):
    """Process-local directory used by tests and one-off scripts."""

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, str]] = {}
        self._lock = threading.Lock()

    def lookup(self, public_id: str) -> Optional[str]:
        with self._lock:
            entry = self._entries.get(public_id)
            return entry["base_url"] if entry else None

    def add(self, public_id: str, base_url: str, account_id: str) -> None:
        if not isinstance(public_id, str) or not public_id:
            raise ValueError("public_id must be a non-empty string")
        _validate_url(base_url)
        _validate_account_id(account_id)
        with self._lock:
            self._entries[public_id] = {
                "public_id": public_id,
                "base_url": base_url,
                "account_id": account_id,
            }

    def remove(self, public_id: str) -> bool:
        with self._lock:
            if public_id in self._entries:
                del self._entries[public_id]
                return True
            return False

    def all_entries(self) -> list[tuple[str, str, str]]:
        with self._lock:
            return [
                (e["public_id"], e["base_url"], e["account_id"])
                for e in self._entries.values()
            ]


__all__ = [
    "InMemoryDirectory",
    "NaradaDirectory",
    "LocalContactList",
]
