"""Nostr relay abstraction with multi-relay support.

NIP-01 defines the relay communication protocol:

    Client -> Relay: ["EVENT", <event>]
    Client -> Relay: ["REQ", <sub_id>, <filter>...]
    Client -> Relay: ["CLOSE", <sub_id>]

    Relay -> Client: ["OK", <event_id>, <success>, <message>]
    Relay -> Client: ["EVENT", <sub_id>, <event>]
    Relay -> Client: ["EOSE", <sub_id>]

This module implements:

* :class:`NostrRelay` -- single relay connection (WebSocket-based)
* :class:`RelayPool` -- manages multiple relays with failover

Design principles:

* The application should NOT depend on a single relay.
* If Relay A fails, Relay B and C continue to work.
* Reconnection is handled automatically.
* Duplicate events from multiple relays are detected.
* Events are validated before acceptance.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .events import NostrEvent, NostrFilter

log = logging.getLogger("nostr.relay")


# --- Relay connection status ------------------------------------------------


@dataclass
class RelayStatus:
    """Status of a relay connection."""

    url: str
    connected: bool = False
    last_connected_at: Optional[int] = None
    last_error: Optional[str] = None
    reconnect_count: int = 0


# --- Single relay -----------------------------------------------------------


class NostrRelay:
    """A single Nostr relay connection.

    Manages WebSocket connection, event publishing, and subscriptions.
    Uses websockets library for async WebSocket communication.

    Parameters
    ----------
    url:
        The relay WebSocket URL (e.g. "wss://relay.damus.io").
    timeout_seconds:
        Connection and message timeout in seconds.
    max_reconnect_delay:
        Maximum delay between reconnection attempts (exponential backoff).
    """

    def __init__(
        self,
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_reconnect_delay: float = 60.0,
    ) -> None:
        self.url = url.rstrip("/")
        self._timeout = timeout_seconds
        self._max_reconnect_delay = max_reconnect_delay
        self._ws = None
        self._status = RelayStatus(url=self.url)
        self._subscriptions: dict[str, dict[str, Any]] = {}
        self._event_callbacks: dict[str, Callable[[NostrEvent], None]] = {}
        self._lock = asyncio.Lock() if hasattr(asyncio, "Lock") else None

    @property
    def status(self) -> RelayStatus:
        return self._status

    @property
    def is_connected(self) -> bool:
        return self._status.connected

    async def connect(self) -> bool:
        """Connect to the relay. Returns True on success."""
        try:
            import websockets
            self._ws = await asyncio.wait_for(
                websockets.connect(self.url),
                timeout=self._timeout,
            )
            self._status.connected = True
            self._status.last_connected_at = int(time.time())
            self._status.last_error = None
            log.info("Connected to relay %s", self.url)
            return True
        except Exception as exc:
            self._status.connected = False
            self._status.last_error = str(exc)
            log.warning("Failed to connect to %s: %s", self.url, exc)
            return False

    async def disconnect(self) -> None:
        """Disconnect from the relay."""
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._status.connected = False
        log.info("Disconnected from relay %s", self.url)

    async def publish(self, event: NostrEvent) -> tuple[bool, str]:
        """Publish an event to the relay.

        NIP-01: Client sends ["EVENT", <event>]
        Relay responds: ["OK", <event_id>, <success>, <message>]

        Returns (success, message).
        """
        if not self._status.connected:
            connected = await self.connect()
            if not connected:
                return False, f"Not connected to {self.url}"

        message = json.dumps(["EVENT", event.to_dict()])
        try:
            import websockets
            await asyncio.wait_for(
                self._ws.send(message),
                timeout=self._timeout,
            )
            # Wait for OK response
            response = await asyncio.wait_for(
                self._ws.recv(),
                timeout=self._timeout,
            )
            data = json.loads(response)
            if isinstance(data, list) and len(data) >= 4 and data[0] == "OK":
                success = data[2]
                msg = data[3] if len(data) > 3 else ""
                return success, msg
            return False, f"Unexpected response: {data}"
        except Exception as exc:
            self._status.last_error = str(exc)
            log.warning("Publish failed to %s: %s", self.url, exc)
            return False, str(exc)

    async def subscribe(
        self,
        subscription_id: str,
        filters: list[NostrFilter],
        on_event: Optional[Callable[[NostrEvent], None]] = None,
    ) -> bool:
        """Subscribe to events matching the given filters.

        NIP-01: Client sends ["REQ", <sub_id>, <filter>...]
        Relay responds with: ["EVENT", <sub_id>, <event>] and ["EOSE", <sub_id>]

        Parameters
        ----------
        subscription_id:
            A unique identifier for this subscription.
        filters:
            List of filters to apply.
        on_event:
            Callback invoked for each matching event.

        Returns
        -------
        bool
            True if the subscription was sent successfully.
        """
        if not self._status.connected:
            connected = await self.connect()
            if not connected:
                return False

        self._subscriptions[subscription_id] = {
            "filters": filters,
            "on_event": on_event,
        }
        if on_event is not None:
            self._event_callbacks[subscription_id] = on_event

        message = json.dumps(
            ["REQ", subscription_id] + [f.to_dict() for f in filters]
        )
        try:
            import websockets
            await asyncio.wait_for(
                self._ws.send(message),
                timeout=self._timeout,
            )
            log.debug("Subscribed to %s on %s", subscription_id, self.url)
            return True
        except Exception as exc:
            self._status.last_error = str(exc)
            log.warning("Subscribe failed to %s: %s", self.url, exc)
            return False

    async def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from a subscription.

        NIP-01: Client sends ["CLOSE", <sub_id>]
        """
        self._subscriptions.pop(subscription_id, None)
        self._event_callbacks.pop(subscription_id, None)

        if not self._status.connected:
            return True

        message = json.dumps(["CLOSE", subscription_id])
        try:
            import websockets
            await asyncio.wait_for(
                self._ws.send(message),
                timeout=self._timeout,
            )
            return True
        except Exception:
            return False

    async def receive_events(self, max_events: int = 100, timeout: float = 10.0) -> list[NostrEvent]:
        """Receive events from active subscriptions.

        This is a simple polling approach for synchronous callers.
        For production use, prefer the callback-based subscribe().

        Returns up to ``max_events`` events within ``timeout`` seconds.
        """
        if not self._status.connected:
            return []

        events: list[NostrEvent] = []
        try:
            import websockets
            deadline = time.time() + timeout
            while len(events) < max_events and time.time() < deadline:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(
                        self._ws.recv(),
                        timeout=remaining,
                    )
                    data = json.loads(raw)
                    if isinstance(data, list) and len(data) >= 3:
                        if data[0] == "EVENT":
                            event = NostrEvent.from_dict(data[2])
                            events.append(event)
                            sub_id = data[1] if len(data) > 1 else None
                            callback = self._event_callbacks.get(sub_id)
                            if callback:
                                try:
                                    callback(event)
                                except Exception:
                                    pass
                        elif data[0] == "EOSE":
                            break
                except asyncio.TimeoutError:
                    break
        except Exception as exc:
            log.warning("Receive failed from %s: %s", self.url, exc)
        return events

    async def reconnect(self) -> bool:
        """Attempt to reconnect with exponential backoff."""
        delay = min(1.0 * (2 ** self._status.reconnect_count), self._max_reconnect_delay)
        self._status.reconnect_count += 1
        log.info("Reconnecting to %s in %.1fs (attempt %d)",
                 self.url, delay, self._status.reconnect_count)
        await asyncio.sleep(delay)
        return await self.connect()


# --- Relay pool (multi-relay) -----------------------------------------------


class RelayPool:
    """Manages multiple Nostr relays with failover and deduplication.

    The pool tries multiple relays in priority order. If the first
    relay fails, it falls back to the next one. Events from multiple
    relays are deduplicated by event id.

    Parameters
    ----------
    relay_urls:
        List of relay WebSocket URLs.
    timeout_seconds:
        Per-relay connection timeout.
    """

    def __init__(
        self,
        relay_urls: Optional[list[str]] = None,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._relays: list[NostrRelay] = []
        self._seen_events: dict[str, int] = {}  # event_id -> timestamp
        self._dedup_window_seconds = 300  # 5 minutes
        for url in (relay_urls or []):
            self._relays.append(NostrRelay(url, timeout_seconds=timeout_seconds))

    @property
    def relays(self) -> list[NostrRelay]:
        return list(self._relays)

    def add_relay(self, url: str, **kwargs: Any) -> NostrRelay:
        """Add a relay to the pool."""
        relay = NostrRelay(url, **kwargs)
        self._relays.append(relay)
        return relay

    def remove_relay(self, url: str) -> bool:
        """Remove a relay from the pool by URL."""
        before = len(self._relays)
        self._relays = [r for r in self._relays if r.url != url]
        return len(self._relays) < before

    def _is_duplicate(self, event_id: str) -> bool:
        """Check if an event was already seen within the dedup window."""
        now = int(time.time())
        expired = [k for k, v in self._seen_events.items()
                   if now - v > self._dedup_window_seconds]
        for k in expired:
            del self._seen_events[k]

        if event_id in self._seen_events:
            return True
        self._seen_events[event_id] = now
        return False

    def clear_dedup_cache(self) -> None:
        """Clear the event deduplication cache."""
        self._seen_events.clear()

    async def connect_all(self) -> int:
        """Connect to all relays. Returns the number of successful connections."""
        connected = 0
        for relay in self._relays:
            if await relay.connect():
                connected += 1
        return connected

    async def disconnect_all(self) -> None:
        """Disconnect from all relays."""
        for relay in self._relays:
            await relay.disconnect()

    async def publish(self, event: NostrEvent) -> tuple[bool, str]:
        """Publish an event to all connected relays.

        Tries each relay in order. Returns True if at least one
        relay accepted the event.
        """
        any_success = False
        last_message = ""
        for relay in self._relays:
            if relay.is_connected:
                success, msg = await relay.publish(event)
                if success:
                    any_success = True
                last_message = msg
        return any_success, last_message

    async def publish_with_failover(self, event: NostrEvent) -> tuple[bool, str]:
        """Publish with failover: try relays until one succeeds.

        Unlike publish(), this stops at the first successful relay.
        """
        for relay in self._relays:
            if relay.is_connected:
                success, msg = await relay.publish(event)
                if success:
                    return True, msg
                log.warning("Publish to %s failed: %s", relay.url, msg)
        return False, "All relays failed"

    async def subscribe(
        self,
        subscription_id: str,
        filters: list[NostrFilter],
        on_event: Optional[Callable[[NostrEvent], None]] = None,
    ) -> int:
        """Subscribe to events across all connected relays.

        Returns the number of relays that accepted the subscription.
        """
        subscribed = 0
        for relay in self._relays:
            if relay.is_connected:
                def _dedup_callback(
                    evt: NostrEvent,
                    _relay: NostrRelay = relay,
                    _cb: Optional[Callable[[NostrEvent], None]] = on_event,
                ) -> None:
                    if not self._is_duplicate(evt.id):
                        if _cb:
                            _cb(evt)

                if await relay.subscribe(
                    f"{subscription_id}_{relay.url}",
                    filters,
                    on_event=_dedup_callback if on_event else None,
                ):
                    subscribed += 1
        return subscribed

    async def unsubscribe_all(self, subscription_id: str) -> None:
        """Unsubscribe from all relays."""
        for relay in self._relays:
            sub_id = f"{subscription_id}_{relay.url}"
            await relay.unsubscribe(sub_id)

    def connected_count(self) -> int:
        """Return the number of currently connected relays."""
        return sum(1 for r in self._relays if r.is_connected)

    def status_summary(self) -> list[RelayStatus]:
        """Return the status of all relays."""
        return [r.status for r in self._relays]


__all__ = [
    "NostrRelay",
    "RelayPool",
    "RelayStatus",
]
