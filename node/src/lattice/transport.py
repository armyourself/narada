"""Lattice transport layer (Phase 2 MVP).

A :class:`LatticeTransport` is the thing that physically moves an
envelope from one node to another. The MVP ships a single concrete
implementation, :class:`HttpLatticeTransport`, that talks plain HTTP
to the recipient's node over loopback. Future work (Phase 3+) can
add QUIC, libp2p, or a relay-based transport without changing the
rest of the package.

The transport is intentionally narrow: it does **not** retry, queue,
or do anything smart with errors. Retry and queueing live in
:mod:`.outbox`. The transport raises :class:`LatticeTransportError`
on any failure (connection refused, non-2xx response, timeout) and
the caller decides what to do.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Mapping, Optional

from .envelope import LatticeEnvelopeError


class LatticeTransportError(LatticeEnvelopeError):
    """Raised by :class:`LatticeTransport` on any delivery failure."""


class LatticeTransport(ABC):
    """Abstract Lattice transport."""

    @abstractmethod
    def send(self, recipient_base_url: str, envelope: Mapping[str, Any]) -> None:
        """Ship ``envelope`` (already sealed) to the recipient at ``base_url``.

        Raises :class:`LatticeTransportError` on any failure. The
        caller is responsible for retry / queueing.
        """


class HttpLatticeTransport(LatticeTransport):
    """Send envelopes as JSON over loopback HTTP.

    The transport is blocking (uses ``urllib`` rather than an async
    HTTP client) because the outbox drainer runs in a worker thread.
    For the MVP this is the right trade-off: no new dependencies,
    simple error model, good enough for tens of pending messages.
    """

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._timeout = timeout_seconds

    def send(self, recipient_base_url: str, envelope: Mapping[str, Any]) -> None:
        base = (recipient_base_url or "").rstrip("/")
        if not base:
            raise LatticeTransportError("recipient base url is empty")
        url = f"{base}/lattice/inbox"
        body = _encode_json(envelope)
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                status = getattr(resp, "status", None) or resp.getcode()
        except urllib.error.HTTPError as exc:
            # Read the response body for a stable error message; cap it
            # so a malicious / huge error page can't OOM us.
            detail = exc.read(2048).decode("utf-8", errors="replace")
            raise LatticeTransportError(
                f"recipient returned HTTP {exc.code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise LatticeTransportError(
                f"could not reach recipient at {url}: {exc.reason}"
            ) from exc
        except (TimeoutError, OSError) as exc:
            raise LatticeTransportError(
                f"transport error talking to {url}: {exc}"
            ) from exc
        if not (200 <= int(status) < 300):
            raise LatticeTransportError(
                f"recipient returned unexpected status {status}"
            )


def _encode_json(mapping: Mapping[str, Any]) -> bytes:
    import json
    return json.dumps(mapping, separators=(",", ":")).encode("utf-8")


__all__ = [
    "HttpLatticeTransport",
    "LatticeTransport",
    "LatticeTransportError",
]
