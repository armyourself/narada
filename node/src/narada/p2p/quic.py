"""QUIC transport for Narada peer-to-peer traffic (Phase 3).

This commit ships the **outbound** side: a drop-in
:class:`src.narada.transport.NaradaTransport` that delivers
envelopes to peer Narada nodes over QUIC instead of HTTP. The
listener is added in commit 5 (message sync) where it can share the
inbox-handler plumbing.

Wire layout (one JSON object per QUIC stream)::

    [4 bytes big-endian length N][N bytes of UTF-8 JSON]

Max payload: 64 KiB. Narada envelopes are well under this; the cap
exists to bound memory if a peer misbehaves.

TOFU pinning: peer cert verification is disabled at the TLS layer
because the application layer pins certs via ``NaradaQuicListener``
(installed in commit 5). Real node authentication is the application
layer — envelope and ack signatures are already cryptographically
bound to a node id.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
from typing import Any, Mapping, Optional

from aioquic.asyncio.client import connect
from aioquic.quic.configuration import QuicConfiguration

from src.narada.transport import NaradaTransport, NaradaTransportError
from .tls import NodeTlsMaterial, _NARADA_ALPN

log = logging.getLogger("narada.p2p.quic")

_MAX_FRAME_BYTES = 64 * 1024
_DEFAULT_QUIC_PORT = 4440


class QuicPeerError(NaradaTransportError):
    """Raised when a QUIC peer misbehaves or the connection fails."""


def _encode_frame(payload: Mapping[str, Any]) -> bytes:
    body = json.dumps(dict(payload), separators=(",", ":")).encode("utf-8")
    if len(body) > _MAX_FRAME_BYTES:
        raise QuicPeerError(f"frame too large: {len(body)}")
    return struct.pack(">I", len(body)) + body


def parse_quic_endpoint(value: str, *, default_port: int = _DEFAULT_QUIC_PORT) -> tuple[str, int]:
    """Parse ``host:port``, ``quic://host:port``, or ``host``.

    Returns ``(host, port)``. Raises :class:`QuicPeerError` on a bad
    value. The ``host`` segment is taken as-is; the caller is
    responsible for any DNS resolution (aioquic does its own).
    """
    s = (value or "").strip()
    if not s:
        raise QuicPeerError("empty endpoint")
    if "://" in s:
        _scheme, _, rest = s.partition("://")
        s = rest
    if ":" in s:
        host, _, port_str = s.rpartition(":")
        host = host.strip()
        try:
            return host, int(port_str)
        except ValueError as exc:
            raise QuicPeerError(f"bad port in {value!r}") from exc
    return s, default_port


class QuicNaradaTransport(NaradaTransport):
    """Outbound QUIC transport for Narada envelopes.

    Each :meth:`send` opens a fresh QUIC connection, ships one frame,
    and closes. The outbox drainer runs in a worker thread and the
    simple model is easier to reason about; pooling lands in a
    later commit.
    """

    def __init__(
        self,
        tls: NodeTlsMaterial,
        *,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._tls = tls
        self._timeout = timeout_seconds

    def _config(self, server_name: str) -> QuicConfiguration:
        cfg = QuicConfiguration(
            alpn_protocols=[_NARADA_ALPN.decode("ascii")],
            is_client=True,
            server_name=server_name,
        )
        # aioquic's load_cert_chain expects file paths, not bytes. Write
        # the on-disk material to short-lived temp files.
        import tempfile
        cert_path = tempfile.NamedTemporaryFile(
            suffix=".pem", delete=False
        )
        cert_path.write(self._tls.cert_pem)
        cert_path.close()
        key_path = tempfile.NamedTemporaryFile(
            suffix=".pem", delete=False
        )
        key_path.write(self._tls.key_pem)
        key_path.close()
        cfg.load_cert_chain(cert_path.name)
        # Verification is disabled at the TLS layer; the listener pins
        # peer certs via TOFU (see NaradaQuicListener in commit 5).
        cfg.verify_mode = False  # type: ignore[assignment]
        return cfg

    def send(self, recipient_endpoint: str, envelope: Mapping[str, Any]) -> None:
        host, port = parse_quic_endpoint(recipient_endpoint)
        try:
            asyncio.run(self._send_async(host, port, envelope))
        except QuicPeerError as exc:
            raise NaradaTransportError(f"QUIC send failed: {exc}") from exc

    def send_with_ack(
        self,
        recipient_endpoint: str,
        envelope: Mapping[str, Any],
    ) -> Optional[object]:
        # The Phase 3 QUIC transport is fire-and-forget; acks arrive on
        # a separate push stream (commit 5). Return None here to keep
        # the abstract interface satisfied.
        self.send(recipient_endpoint, envelope)
        return None

    async def _send_async(
        self, host: str, port: int, envelope: Mapping[str, Any]
    ) -> None:
        cfg = self._config(server_name=host)
        try:
            async with asyncio.timeout(self._timeout):
                async with connect(host, port, configuration=cfg) as proto:
                    stream_id = proto._quic.get_next_available_stream_id(
                        is_unidirectional=False
                    )
                    _reader, writer = await proto.open_stream(
                        stream_id, as_pair=True
                    )
                    writer.write(_encode_frame(envelope))
                    await writer.drain()
                    writer.write_eof()
                    await proto.wait_closed()
        except TimeoutError as exc:
            raise QuicPeerError(f"timeout talking to {host}:{port}") from exc
        except (ConnectionError, OSError) as exc:
            raise QuicPeerError(f"could not reach {host}:{port}: {exc}") from exc
        except Exception as exc:
            raise QuicPeerError(f"QUIC error to {host}:{port}: {exc}") from exc


__all__ = [
    "QuicNaradaTransport",
    "QuicPeerError",
    "parse_quic_endpoint",
    "_MAX_FRAME_BYTES",
    "_DEFAULT_QUIC_PORT",
]