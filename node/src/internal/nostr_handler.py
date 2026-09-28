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
            cls._instance._config: Optional[NostrConfig] = None
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
        """Aggregate relay status across all adapters.

        Configured relays that are not (yet) in any adapter pool — e.g.
        added while no identity exists, or a just-added URL that failed
        to connect — are reported too, so the UI list matches config.
        """
        seen_urls: set[str] = set()
        statuses: list[dict] = []
        for adapter in self._adapters.values():
            for relay in adapter.relay_pool.relays:
                if relay.url.lower() not in seen_urls:
                    seen_urls.add(relay.url.lower())
                    statuses.append({
                        "url": relay.url,
                        "connected": relay.is_connected,
                        "last_error": relay.status.last_error,
                        "last_connected_at": relay.status.last_connected_at,
                        "reconnect_count": relay.status.reconnect_count,
                    })
        for url in self.get_config().relay_urls:
            if url.lower() not in seen_urls:
                seen_urls.add(url.lower())
                statuses.append({
                    "url": url,
                    "connected": False,
                    "last_error": None,
                    "last_connected_at": None,
                    "reconnect_count": 0,
                })
        return statuses

    # -- relay configuration -----------------------------------------------

    def _config_path(self) -> Path:
        from src.consts import APP_NAME
        data_dir = Path(os.path.expanduser("~")) / f".{APP_NAME.lower()}"
        return data_dir / "etc" / "config.json"

    def get_config(self) -> NostrConfig:
        """Relay/transport config, loaded once from ``~/.…/etc/config.json``."""
        if self._config is None:
            self._config = NostrConfig.from_file(self._config_path())
        return self._config

    def add_relay(self, url: str) -> tuple[bool, str]:
        """Persist a new relay URL and roll it out to every adapter."""
        from src.nostr.config import normalize_relay_url
        try:
            normalized = normalize_relay_url(url)
        except ValueError as exc:
            return False, str(exc)

        config = self.get_config()
        known = {entry.rstrip("/").lower() for entry in config.relay_urls}
        if normalized.lower() in known:
            return False, f"Relay already configured: {normalized}"

        config.relay_urls.append(normalized)
        config.save(self._config_path())

        results: list[str] = []
        for account_id, adapter in self._adapters.items():
            try:
                ok, msg = adapter.add_relay(normalized)
                if not ok:
                    results.append(f"{account_id}: {msg}")
                    uvicorn_logger.warning(
                        f"Runtime relay add for {account_id} reported: {msg}"
                    )
            except Exception as exc:
                results.append(f"{account_id}: {exc}")
                uvicorn_logger.error(
                    f"Failed to add relay {normalized} for {account_id}: {exc}"
                )
        if results:
            return True, (
                f"Relay configured but not fully live — "
                f"{'; '.join(results)}"
            )
        return True, f"Relay added: {normalized}"

    def remove_relay(self, url: str) -> tuple[bool, str]:
        """Drop a relay from config and disconnect it everywhere."""
        from src.nostr.config import normalize_relay_url
        try:
            normalized = normalize_relay_url(url)
        except ValueError as exc:
            return False, str(exc)

        config = self.get_config()
        remaining = [
            entry
            for entry in config.relay_urls
            if entry.rstrip("/").lower() != normalized.lower()
        ]
        if len(remaining) == len(config.relay_urls):
            return False, f"Relay not configured: {normalized}"
        if not remaining:
            return False, "Cannot remove the last configured relay"

        config.relay_urls = remaining
        config.save(self._config_path())

        for account_id, adapter in self._adapters.items():
            try:
                adapter.remove_relay(normalized)
            except Exception as exc:
                uvicorn_logger.error(
                    f"Failed to remove relay {normalized} for {account_id}: {exc}"
                )
        return True, f"Relay removed: {normalized}"

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
        # Recovered identities used to be persisted with an empty npub;
        # always derive from the key so stored npubs stay NIP-19-valid even
        # if a caller passes a stale or malformed value.
        npub = identity.public_key_bech32

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

    def delete_identity(self, account_id: str) -> tuple[bool, str]:
        """Delete a stored Nostr identity for *account_id*.

        Disconnects and drops the live adapter **and** removes the
        persisted ``nostr_identity.<account>.json`` file — without the
        file removal the identity resurrects on the next boot when
        ``load_stored_identities`` rescans the etc directory.
        """
        adapter = self._adapters.pop(account_id, None)
        if adapter is not None:
            try:
                adapter.disconnect()
            except Exception as exc:
                uvicorn_logger.error(
                    f"Failed to disconnect Nostr adapter for {account_id}: {exc}"
                )

        path = self._identity_path(account_id)
        existed = path.exists()
        if existed:
            try:
                path.unlink()
            except OSError as exc:
                return False, f"Failed to delete identity file: {exc}"

        if adapter is None and not existed:
            return False, f"No Nostr identity for {account_id}"
        uvicorn_logger.info(f"Deleted Nostr identity for {account_id}")
        return True, f"Identity deleted for {account_id}"

    def load_stored_identities(
        self, config: Optional[NostrConfig] = None
    ) -> dict[str, NostrAdapter]:
        """Load previously stored Nostr identities and create adapters.

        Scans ``<data_dir>/etc/nostr_identity.<account_id>.json`` for
        each stored identity, creates a NostrAdapter, and connects it.

        Returns a dict of account_id -> adapter.
        """
        etc_dir = self._identity_dir()

        if not etc_dir.exists():
            return {}

        loaded: dict[str, NostrAdapter] = {}
        prefix, suffix = "nostr_identity.", ".json"
        for path in etc_dir.glob(f"{prefix}*{suffix}"):
            # Extract account_id from filename: nostr_identity.<account_id>.json
            # (splitting on "." broke accounts whose address itself contains
            # dots — e.g. "user.name@example.com" reloaded as "name@example")
            account_id = path.name[len(prefix):-len(suffix)]
            if not account_id:
                continue

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

    def _identity_dir(self) -> Path:
        from src.consts import APP_NAME
        data_dir = Path(os.path.expanduser("~")) / f".{APP_NAME.lower()}"
        return data_dir / "etc"

    def _identity_path(self, account_id: str) -> Path:
        safe = "".join(
            c if c.isalnum() or c in "._@+-" else "_" for c in account_id
        ) or "unknown"
        return self._identity_dir() / f"nostr_identity.{safe}.json"


__all__ = ["NostrHandler"]
