"""Outbound relay client (Phase 4).

A small async client that talks to a peer Narada node over the
existing QUIC transport and ships ``relay.deposit`` /
``relay.fetch`` / ``relay.drop`` frames.

The framing helpers live in
:mod:`src.narada.p2p.listener` (``encode_frame`` /
``decode_frame``) so relay frames are wire-compatible with every
other Narada frame.

Tests do not need to spin aioquic up; they use :class:`InProcessRelayTransport`
in :mod:`src.narada.relay.testing` instead.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
from typing import Any, Mapping, Optional

from aioquic.asyncio.client import connect
from aioquic.quic.configuration import QuicConfiguration

from src.narada_security.hmac_io import hmac_io_key  # noqa: F401  (used by callers)
from src.narada.p2p.listener import decode_frame, encode_frame
from src.narada.p2p.quic import parse_quic_endpoint
from src.narada.p2p.tls import NodeTlsMaterial


log = logging.getLogger("narada.relay.transport")

_MAX_FRAME_BYTES = 64 * 1024


class RelayClientError(Exception):
    """Raised by :class:`RelayClient` on any failure."""


class RelayClient:
    """Single-shot QUIC client for relay frames.

    Usage::

        async with RelayClient(tls=my_node_tls) as client:
            receipt = await client.deposit(endpoint, envelope, ttl_seconds=...)
            deposits = await client.fetch(endpoint, recipient_public_id=...)

    The client opens a fresh QUIC connection per request to keep the
    state machine simple. Phase 4+ may pool connections.
    """

    def __init__(
        self,
        *,
        tls: NodeTlsMaterial,
        server_name: Optional[str] = None,
    ) -> None:
        self._tls = tls
        self._server_name = server_name

    async def deposit(
        self,
        endpoint: str,
        envelope: Mapping[str, Any],
        *,
        ttl_seconds: Optional[int] = None,
    ) -> dict:
        host, port = parse_quic_endpoint(endpoint)
        payload = {
            "type": "relay.deposit",
            "v": 1,
            "envelope": dict(envelope),
        }
        if ttl_seconds is not None:
            payload["expires_at"] = int(ttl_seconds)
        return await self._request(host, port, payload)

    async def fetch(
        self,
        endpoint: str,
        *,
        recipient_public_id: str,
        limit: int = 64,
    ) -> dict:
        host, port = parse_quic_endpoint(endpoint)
        payload = {
            "type": "relay.fetch",
            "v": 1,
            "recipient_public_id": recipient_public_id,
            "limit": int(limit),
        }
        return await self._request(host, port, payload)

    async def drop(
        self,
        endpoint: str,
        *,
        recipient_public_id: str,
        deposit_ids: list,
    ) -> dict:
        host, port = parse_quic_endpoint(endpoint)
        payload = {
            "type": "relay.drop",
            "v": 1,
            "recipient_public_id": recipient_public_id,
            "deposit_ids": list(deposit_ids),
        }
        return await self._request(host, port, payload)

    # --- Wire ---------------------------------------------------------

    async def _request(self, host: str, port: int, payload: dict) -> dict:
        cfg = QuicConfiguration(
            alpn_protocols=[b"narada/1"],
            is_client=True,
            server_name=self._server_name or host,
        )
        cfg.load_cert_chain(self._tls.cert_pem)
        cfg.load_private_key(self._tls.key_pem)
        # Peer cert verification is intentionally disabled at the TLS
        # layer; relay nodes trust peers via TOFU pinning on first
        # contact (Phase 3 commit 5).
        cfg.verify_mode = False  # type: ignore[attr-defined]
        async with connect(
            host,
            port,
            configuration=cfg,
            create_protocol=None,
        ) as protocol:
            stream_handle, _ = await protocol.create_stream()
            frame = encode_frame(payload)
            stream_handle.write(frame)
            await stream_handle.flush()
            # Read one length-prefixed frame back.
            header = await _read_exact(stream_handle, 4)
            (length,) = struct.unpack(">I", header)
            if length > _MAX_FRAME_BYTES:
                raise RelayClientError(
                    f"reply frame too large: {length}"
                )
            body = await _read_exact(stream_handle, length)
            try:
                return decode_frame(header + body)
            except Exception as exc:
                raise RelayClientError(f"reply not valid frame: {exc}") from exc

    async def __aenter__(self) -> "RelayClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        # The per-request ``async with connect`` handles teardown.
        return None


async def _read_exact(handle, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = await handle.read(n - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    if len(buf) != n:
        raise RelayClientError(f"short read: wanted {n}, got {len(buf)}")
    return bytes(buf)


__all__ = ["RelayClient", "RelayClientError"]
