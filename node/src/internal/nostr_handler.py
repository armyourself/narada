"""Singleton managing NostrAdapter instances alongside Openmail clients.

Mirrors the ClientHandler pattern: one adapter per account, created at
startup from stored identities, and lazily available for the routers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from src.helpers.uvicorn_logger import UvicornLogger
from src.nostr.adapter import NostrAdapter
from src.nostr.config import NostrConfig
from src.nostr.identity import NostrIdentity, npub_decode

uvicorn_logger = UvicornLogger()

type NostrAdapters = dict[str, NostrAdapter]


class NostrHandler:
    """Singleton that owns NostrAdapter instances keyed by account id.

    The account id is the email address associated with the Nostr identity.
    """

    _instance: Optional[NostrHandler] = None

    def __new__(cls) -> NostrHandler:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._adapters: NostrAdapters = {}
        return cls._instance

    # -- lifecycle ----------------------------------------------------------

    def create_adapter(
        self,
        account_id: str,
        *,
        identity: Optional[NostrIdentity] = None,
        config: Optional[NostrConfig] = None,
    ) -> NostrAdapter:
        """Create (or replace) a NostrAdapter for *account_id*."""
        adapter = NostrAdapter(
            account_id,
            identity=identity,
            config=config,
        )
        self._adapters[account_id] = adapter
        return adapter

    def connect_adapter(self, account_id: str) -> tuple[bool, str]:
        """Connect the adapter for *account_id* to its relays."""
        adapter = self._adapters.get(account_id)
        if adapter is None:
            return False, f"No Nostr adapter for {account_id}"
        return adapter.connect()

    def connect_all(self) -> dict[str, tuple[bool, str]]:
        """Connect every registered adapter. Returns per-account results."""
        results: dict[str, tuple[bool, str]] = {}
        for account_id, adapter in self._adapters.items():
            results[account_id] = adapter.connect()
        return results

    def shutdown(self) -> None:
        """Disconnect all adapters."""
        for account_id, adapter in self._adapters.items():
            try:
                adapter.disconnect()
            except Exception as exc:
                uvicorn_logger.error(
                    f"Failed to disconnect Nostr adapter for {account_id}: {exc}"
                )
        self._adapters.clear()

    # -- accessors ----------------------------------------------------------

    def get_adapter(self, account_id: str) -> Optional[NostrAdapter]:
        return self._adapters.get(account_id)

    def has_adapter(self, account_id: str) -> bool:
        return account_id in self._adapters

    def get_all_adapters(self) -> NostrAdapters:
        return dict(self._adapters)

    def get_relay_status(self) -> list[dict]:
        """Aggregate relay status across all adapters."""
        seen_urls: set[str] = set()
        statuses: list[dict] = []
        for adapter in self._adapters.values():
            for relay in adapter.relay_pool.relays:
                if relay.url not in seen_urls:
                    seen_urls.add(relay.url)
                    statuses.append({
                        "url": relay.url,
                        "connected": relay.is_connected,
                        "last_error": relay.status.last_error,
                    })
        return statuses

    # -- identity storage ---------------------------------------------------

    def store_identity(
        self,
        account_id: str,
        npub: str,
        nsec_hex: str,
        *,
        config: Optional[NostrConfig] = None,
    ) -> NostrAdapter:
        """Store a Nostr identity and create an adapter for *account_id*.

        Called by the ``/nostr/register-identity`` endpoint after the
        client generates or recovers a Nostr identity.

        Parameters
        ----------
        account_id:
            The email address that owns this identity.
        npub:
            The npub-encoded public key (for display / verification).
        nsec_hex:
            The hex-encoded 32-byte secret key used to derive the identity.
        config:
            Optional Nostr transport configuration.
        """
        secret_bytes = bytes.fromhex(nsec_hex)
        identity = NostrIdentity.from_secret_key(secret_bytes)

        # Persist to data dir so adapters survive restarts.
        identity_path = self._identity_path(account_id)
        identity_path.parent.mkdir(parents=True, exist_ok=True)
        identity_path.write_text(
            json.dumps({
                "npub": npub,
                "nsec_hex": nsec_hex,
            }),
            encoding="utf-8",
        )

        adapter = self.create_adapter(account_id, identity=identity, config=config)
        uvicorn_logger.info(
            f"Registered Nostr identity for {account_id}: {npub[:16]}..."
        )
        return adapter

    def load_stored_identities(
        self, config: Optional[NostrConfig] = None
    ) -> dict[str, NostrAdapter]:
        """Load previously stored Nostr identities and create adapters.

        Scans ``<data_dir>/etc/nostr_identity.<account_id>.json`` for
        each stored identity, creates a NostrAdapter, and connects it.

        Returns a dict of account_id -> adapter.
        """
        from src.consts import APP_NAME
        data_dir = Path(os.path.expanduser("~")) / f".{APP_NAME.lower()}"
        etc_dir = data_dir / "etc"

        if not etc_dir.exists():
            return {}

        loaded: dict[str, NostrAdapter] = {}
        for path in etc_dir.glob("nostr_identity.*.json"):
            # Extract account_id from filename: nostr_identity.<account_id>.json
            stem = path.stem  # nostr_identity.<account_id>
            parts = stem.split(".", 2)
            if len(parts) < 3:
                continue
            account_id = parts[2]

            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                nsec_hex = data.get("nsec_hex", "")
                if not nsec_hex:
                    continue

                secret_bytes = bytes.fromhex(nsec_hex)
                identity = NostrIdentity.from_secret_key(secret_bytes)
                adapter = self.create_adapter(account_id, identity=identity, config=config)
                loaded[account_id] = adapter
                uvicorn_logger.info(
                    f"Loaded stored Nostr identity for {account_id}"
                )
            except Exception as exc:
                uvicorn_logger.error(
                    f"Failed to load Nostr identity from {path}: {exc}"
                )

        return loaded

    def _identity_path(self, account_id: str) -> Path:
        from src.consts import APP_NAME
        safe = "".join(
            c if c.isalnum() or c in "._@+-" else "_" for c in account_id
        ) or "unknown"
        data_dir = Path(os.path.expanduser("~")) / f".{APP_NAME.lower()}"
        return data_dir / "etc" / f"nostr_identity.{safe}.json"


__all__ = ["NostrHandler"]
