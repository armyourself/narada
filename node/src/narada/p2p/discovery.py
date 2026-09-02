"""Peer discovery for Narada (Phase 3 commit 2).

A Narada node finds its peers via two complementary mechanisms:

1. **mDNS / DNS-SD** (``zeroconf``) — broadcast our QUIC endpoint on
   the LAN under the service name ``_narada._udp.local.``. Other
   nodes that listen on the same LAN pick us up automatically.
   mDNS works on Linux, macOS, and (with some caveats) Windows.

2. **Bootstrap list** — a plain text file at
   ``<data_dir>/node_identity/bootstrap_peers.txt`` with one
   ``host:port`` per line. Lines starting with ``#`` are comments.
   This is the WAN fallback when mDNS does not traverse the network
   boundary. A node can also learn new peers by accepting incoming
   QUIC connections (their host:port is added to the discovered set).

The two paths share a single in-memory :class:`PeerTable` that the
directory consults when looking up a recipient's base URL. Persisting
the table is the job of commit 7 (node failure handling); this
commit only populates it.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from zeroconf import (
    ServiceBrowser,
    ServiceInfo,
    ServiceListener,
    Zeroconf,
    ServiceStateChange,
)

from .tls import NodeTlsMaterial

log = logging.getLogger("narada.p2p.discovery")

_MDNS_SERVICE = "_narada._udp.local."
_DEFAULT_QUIC_PORT = 4440


@dataclass(frozen=True)
class DiscoveredPeer:
    """A peer node we have learned about.

    ``quic_endpoint`` is ``"host:port"`` (host may be a hostname or
    an IP literal). ``node_public_id`` is the peer's ``node1...``
    identity when we have one; the mDNS path includes it in the TXT
    record so the first-contact lookup is unambiguous.
    """

    quic_endpoint: str
    node_public_id: Optional[str] = None
    via: str = "unknown"  # "mdns", "bootstrap", or "inbound"
    last_seen: float = field(default_factory=time.time)

    def host_port(self) -> tuple[str, int]:
        host, _, port_str = self.quic_endpoint.rpartition(":")
        return host, int(port_str or _DEFAULT_QUIC_PORT)


# --- Bootstrap list ------------------------------------------------------


def parse_bootstrap_file(path: Path) -> list[str]:
    """Read a bootstrap peers file. One ``host:port`` per line.

    Blank lines and ``#`` comments are ignored. Malformed lines are
    skipped with a log warning so a single typo doesn't break startup.
    """
    out: list[str] = []
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            log.warning("bootstrap line %r has no port; skipping", line)
            continue
        out.append(line)
    return out


# --- mDNS responder + /


def _mdns_txt_properties(node_public_id: Optional[str]) -> dict[bytes, bytes | None]:
    props: dict[bytes, bytes | None] = {
        b"version": b"1",
    }
    if node_public_id:
        props[b"node_id"] = node_public_id.encode("ascii")
    return props


class _Listener(ServiceListener):
    """Bridges zeroconf callbacks into a :class:`PeerTable`."""

    def __init__(self, table: "PeerTable") -> None:
        self._table = table

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info is None:
            return
        self._handle(info)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        # We don't actively forget peers on mDNS removal; liveness is
        # the job of commit 7. Keep the entry, age it via last_seen.
        return

    def _handle(self, info: ServiceInfo) -> None:
        addresses = info.parsed_addresses()
        port = info.port
        node_id: Optional[str] = None
        if info.properties:
            raw = info.properties.get(b"node_id")
            if isinstance(raw, bytes):
                try:
                    node_id = raw.decode("ascii")
                except UnicodeDecodeError:
                    node_id = None
        if not addresses:
            return
        host = addresses[0]
        peer = DiscoveredPeer(
            quic_endpoint=f"{host}:{port}",
            node_public_id=node_id,
            via="mdns",
        )
        self._table.upsert(peer)


class MdnsAdvertiser:
    """Advertise this node's QUIC endpoint via mDNS."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        node_public_id: Optional[str],
        zc: Optional[Zeroconf] = None,
    ) -> None:
        self._host = host
        self._port = port
        self._node_public_id = node_public_id
        self._zc: Optional[Zeroconf] = zc
        self._info: Optional[ServiceInfo] = None
        self._owns_zc = zc is None

    def start(self) -> None:
        if self._zc is None:
            self._zc = Zeroconf()
        addresses = socket.getaddrinfo(self._host, None)
        # Pick the first IPv4 / IPv6 address we can use.
        ip_bytes: Optional[bytes] = None
        for family, _type, _proto, _canon, sockaddr in addresses:
            if family == socket.AF_INET:
                ip_bytes = socket.inet_aton(sockaddr[0])
                break
        if ip_bytes is None:
            for family, _type, _proto, _canon, sockaddr in addresses:
                if family == socket.AF_INET6:
                    ip_bytes = socket.inet_pton(sockaddr[0])
                    break
        if ip_bytes is None:
            log.warning("mDNS: could not determine local address; skipping advertise")
            return
        self._info = ServiceInfo(
            _MDNS_SERVICE,
            f"Narada-{self._node_public_id or 'anon'}._narada._udp.local.",
            addresses=[ip_bytes],
            port=self._port,
            properties=_mdns_txt_properties(self._node_public_id),
        )
        assert self._zc is not None
        self._zc.register_service(self._info)
        log.info("mDNS: advertising %s on port %s", self._node_public_id, self._port)

    def stop(self) -> None:
        if self._zc is not None and self._info is not None:
            try:
                self._zc.unregister_service(self._info)
            except Exception:
                pass
        if self._owns_zc and self._zc is not None:
            self._zc.close()
        self._info = None
        self._zc = None


class MdnsBrowser:
    """Browse for other Narada nodes via mDNS."""

    def __init__(self, table: "PeerTable", zc: Optional[Zeroconf] = None) -> None:
        self._table = table
        self._zc: Optional[Zeroconf] = zc
        self._browser: Optional[ServiceBrowser] = None
        self._owns_zc = zc is None

    def start(self) -> None:
        if self._zc is None:
            self._zc = Zeroconf()
        listener = _Listener(self._table)
        assert self._zc is not None
        self._browser = ServiceBrowser(
            self._zc, _MDNS_SERVICE, listener=listener
        )
        log.info("mDNS: browsing for %s", _MDNS_SERVICE)

    def stop(self) -> None:
        if self._browser is not None:
            self._browser.cancel()
            self._browser = None
        if self._owns_zc and self._zc is not None:
            self._zc.close()
        self._zc = None


# --- PeerTable -----------------------------------------------------------


class PeerTable:
    """In-memory set of discovered peers.

    Thread-safe. Lookup is by host:port (so we don't collide two
    listeners on the same machine) and by node_public_id (so a
    sender can resolve a recipient's node even if its host changed).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_endpoint: dict[str, DiscoveredPeer] = {}
        self._by_node_id: dict[str, str] = {}  # node_public_id -> endpoint

    def upsert(self, peer: DiscoveredPeer) -> None:
        with self._lock:
            existing = self._by_endpoint.get(peer.quic_endpoint)
            if existing is not None:
                # Refresh, preserving the original 'via' label.
                peer = DiscoveredPeer(
                    quic_endpoint=peer.quic_endpoint,
                    node_public_id=peer.node_public_id or existing.node_public_id,
                    via=existing.via,
                    last_seen=time.time(),
                )
            else:
                peer = DiscoveredPeer(
                    quic_endpoint=peer.quic_endpoint,
                    node_public_id=peer.node_public_id,
                    via=peer.via,
                    last_seen=time.time(),
                )
            self._by_endpoint[peer.quic_endpoint] = peer
            if peer.node_public_id:
                self._by_node_id[peer.node_public_id] = peer.quic_endpoint

    def lookup_by_endpoint(self, endpoint: str) -> Optional[DiscoveredPeer]:
        with self._lock:
            return self._by_endpoint.get(endpoint)

    def lookup_by_node_id(self, node_public_id: str) -> Optional[DiscoveredPeer]:
        with self._lock:
            endpoint = self._by_node_id.get(node_public_id)
            if endpoint is None:
                return None
            return self._by_endpoint.get(endpoint)

    def all_endpoints(self) -> list[str]:
        with self._lock:
            return list(self._by_endpoint.keys())

    def load_bootstrap(self, endpoints: Iterable[str]) -> int:
        n = 0
        for ep in endpoints:
            try:
                host, port_s = ep.rsplit(":", 1)
                int(port_s)
            except (ValueError, IndexError):
                continue
            self.upsert(DiscoveredPeer(quic_endpoint=ep, via="bootstrap"))
            n += 1
        return n

    def remember_inbound(self, host: str, port: int) -> None:
        """Record that a peer reached us at host:port."""
        self.upsert(DiscoveredPeer(quic_endpoint=f"{host}:{port}", via="inbound"))


__all__ = [
    "DiscoveredPeer",
    "MdnsAdvertiser",
    "MdnsBrowser",
    "PeerTable",
    "parse_bootstrap_file",
    "_MDNS_SERVICE",
]