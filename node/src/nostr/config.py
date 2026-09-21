"""Nostr transport configuration.

Defines the configuration for the Nostr adapter, including:

* Default relay URLs
* Transport selection (nostr, legacy_narada, smtp)
* Relay pool settings
* Encryption preferences
* Message retention
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional


# Default Nostr relays (public, well-known relays)
DEFAULT_RELAYS = [
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://relay.nostr.band",
]

# Narada-specific Nostr event kind
NARADA_EMAIL_KIND = 1050


@dataclass
class NostrConfig:
    """Configuration for the Nostr transport.

    Parameters
    ----------
    transport:
        Which transport to use: "nostr", "legacy_narada", or "smtp".
    relay_urls:
        List of Nostr relay WebSocket URLs.
    encryption:
        Encryption method: "nip04" or "nip44". NIP-04 is default
        for broad relay compatibility. NIP-44 is more secure but
        requires both endpoints to support it.
    dedup_window_seconds:
        How long to remember event ids for deduplication (seconds).
    message_retention_days:
        How long relays are expected to keep events (days).
    event_kind:
        Nostr event kind for Narada email messages. Default is 1050.
    timeout_seconds:
        Connection and message timeout.
    auto_reconnect:
        Whether to automatically reconnect on disconnection.
    max_reconnect_attempts:
        Maximum number of reconnection attempts before giving up.
    """

    transport: str = "nostr"
    relay_urls: list[str] = field(default_factory=lambda: list(DEFAULT_RELAYS))
    encryption: str = "nip04"
    dedup_window_seconds: int = 300
    message_retention_days: int = 7
    event_kind: int = NARADA_EMAIL_KIND
    timeout_seconds: float = 30.0
    auto_reconnect: bool = True
    max_reconnect_attempts: int = 10

    def to_dict(self) -> dict[str, Any]:
        """Serialize the config to a dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NostrConfig:
        """Deserialize a config from a dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_file(cls, path: Path | str) -> NostrConfig:
        """Load configuration from a JSON file."""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return cls()

    def save(self, path: Path) -> None:
        """Save configuration to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def default(cls) -> NostrConfig:
        """Return the default configuration."""
        return cls()

    @classmethod
    def from_env(cls) -> NostrConfig:
        """Load configuration from environment variables.

        Environment variables:

        * NARADA_TRANSPORT — transport choice (nostr/legacy_narada/smtp)
        * NARADA_NOSTR_RELAYS — comma-separated relay URLs
        * NARADA_NOSTR_ENCRYPTION — encryption method (nip04/nip44)
        """
        transport = os.environ.get("NARADA_TRANSPORT", "nostr")
        relays_str = os.environ.get("NARADA_NOSTR_RELAYS", "")
        relays = [r.strip() for r in relays_str.split(",") if r.strip()] if relays_str else list(DEFAULT_RELAYS)
        encryption = os.environ.get("NARADA_NOSTR_ENCRYPTION", "nip04")
        return cls(
            transport=transport,
            relay_urls=relays,
            encryption=encryption,
        )


__all__ = ["NARADA_EMAIL_KIND", "DEFAULT_RELAYS", "NostrConfig"]
