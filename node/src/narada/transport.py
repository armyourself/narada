"""Narada transport layer (Phase 2 MVP).

A :class:`NaradaTransport` is the thing that physically moves an
envelope from one node to another. The MVP ships a single concrete
implementation, :class:`HttpNaradaTransport`, that talks plain HTTP
to the recipient's node over loopback. Future work (Phase 3+) can
add QUIC, libp2p, or a relay-based transport without changing the
rest of the package.

The transport is intentionally narrow: it does **not** retry, queue,
or do anything smart with errors. Retry and queueing live in
:mod:`.outbox`. The transport raises :class:`NaradaTransportError`
on any failure (connection refused, non-2xx response, timeout) and
the caller decides what to do.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Mapping, Optional

from .envelope import NaradaEnvelopeError


class NaradaTransportError(NaradaEnvelopeError):
    """Raised by :class:`NaradaTransport` on any delivery failure."""


class NaradaTransport(ABC):
    """Abstract narada transport."""

    @abstractmethod
    def send(
        self, recipient_base_url: str, envelope: Mapping[str, Any]
    ) -> None:
        """Ship ``envelope`` (already sealed) to the recipient at ``base_url``.

        Raises :class:`NaradaTransportError` on any failure. The
        caller is responsible for retry / queueing.

        Implementations are free to ignore the recipient's response
        body. Callers that need the delivery acknowledgement must use
        :meth:`send_with_ack`.
        """

    def send_with_ack(
        self, recipient_base_url: str, envelope: Mapping[str, Any]
    ) -> Optional["NaradaAck"]:
        """Send ``envelope`` and return the recipient's signed ack, if any.

        Default implementation calls :meth:`send` and discards the
        response. Subclasses that talk to a real Narada receiver
        (HTTP today; QUIC / libp2p in Phase 3+) should override this
        to parse the response body.
        """
        self.send(recipient_base_url, envelope)
        return None


class HttpNaradaTransport(NaradaTransport):
    """Send envelopes as JSON over loopback HTTP.

    The transport is blocking (uses ``urllib`` rather than an async
    HTTP client) because the outbox drainer runs in a worker thread.
    For the MVP this is the right trade-off: no new dependencies,
    simple error model, good enough for tens of pending messages.
    """

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._timeout = timeout_seconds

    def send(
        self, recipient_base_url: str, envelope: Mapping[str, Any]
    ) -> None:
        # Delegate to send_with_ack and discard the response.
        self.send_with_ack(recipient_base_url, envelope)

    def send_with_ack(
        self, recipient_base_url: str, envelope: Mapping[str, Any]
    ) -> Optional["NaradaAck"]:
        from .ack import NaradaAck

        base = (recipient_base_url or "").rstrip("/")
        if not base:
            raise NaradaTransportError("recipient base url is empty")
        url = f"{base}/narada/inbox"
        body = _encode_json(envelope)
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        ack: Optional[NaradaAck] = None
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                status = getattr(resp, "status", None) or resp.getcode()
                raw = resp.read(4096)
        except urllib.error.HTTPError as exc:
            # Read the response body for a stable error message; cap it
            # so a malicious / huge error page can't OOM us.
            detail = exc.read(2048).decode("utf-8", errors="replace")
            raise NaradaTransportError(
                f"recipient returned HTTP {exc.code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise NaradaTransportError(
                f"could not reach recipient at {url}: {exc.reason}"
            ) from exc
        except (TimeoutError, OSError) as exc:
            raise NaradaTransportError(
                f"transport error talking to {url}: {exc}"
            ) from exc
        if not (200 <= int(status) < 300):
            raise NaradaTransportError(
                f"recipient returned unexpected status {status}"
            )
        # Best effort; a malformed ack must not fail the send.
        if raw:
            try:
                import json as _json

                parsed = _json.loads(raw.decode("utf-8"))
                if isinstance(parsed, Mapping) and parsed.get("success") is True:
                    data_field = parsed.get("data")
                    if isinstance(data_field, Mapping):
                        ack_data = data_field.get("ack")
                    if isinstance(ack_data, Mapping):
                        try:
                            ack = NaradaAck.from_dict(ack_data)
                        except Exception:
                            ack = None
            except (UnicodeDecodeError, ValueError):
                ack = None
        return ack
