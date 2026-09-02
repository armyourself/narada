"""Tests for the peer discovery module."""

from __future__ import annotations

import socket
import tempfile
from pathlib import Path

import pytest

from src.narada.p2p.discovery import (
    DiscoveredPeer,
    MdnsAdvertiser,
    MdnsBrowser,
    PeerTable,
    _MDNS_SERVICE,
    parse_bootstrap_file,
)


def test_mdns_service_constant():
    # Service name must include the protocol (UDP) and the .local. TLD
    # so zeroconf advertises the right thing.
    assert _MDNS_SERVICE == "_narada._udp.local."


def test_peer_table_upsert_and_lookup():
    pt = PeerTable()
    pt.upsert(DiscoveredPeer(quic_endpoint="10.0.0.1:4440", via="mdns"))
    pt.upsert(DiscoveredPeer(quic_endpoint="10.0.0.2:4440", via="bootstrap"))
    assert pt.lookup_by_endpoint("10.0.0.1:4440") is not None
    assert pt.lookup_by_endpoint("10.0.0.2:4440") is not None
    assert pt.lookup_by_endpoint("10.0.0.3:4440") is None
    assert sorted(pt.all_endpoints()) == ["10.0.0.1:4440", "10.0.0.2:4440"]


def test_peer_table_lookup_by_node_id():
    pt = PeerTable()
    pt.upsert(
        DiscoveredPeer(
            quic_endpoint="10.0.0.1:4440",
            node_public_id="node1abc",
            via="mdns",
        )
    )
    found = pt.lookup_by_node_id("node1abc")
    assert found is not None
    assert found.quic_endpoint == "10.0.0.1:4440"


def test_peer_table_upsert_preserves_via_label():
    pt = PeerTable()
    pt.upsert(DiscoveredPeer(quic_endpoint="10.0.0.1:4440", via="mdns"))
    # Re-upsert with a different via; original should stick.
    pt.upsert(DiscoveredPeer(quic_endpoint="10.0.0.1:4440", via="bootstrap"))
    p = pt.lookup_by_endpoint("10.0.0.1:4440")
    assert p is not None
    assert p.via == "mdns"


def test_peer_table_load_bootstrap():
    pt = PeerTable()
    n = pt.load_bootstrap(["10.0.0.1:4440", "10.0.0.2:4440", "bad"])
    assert n == 2
    assert pt.lookup_by_endpoint("10.0.0.1:4440") is not None
    assert pt.lookup_by_endpoint("bad") is None


def test_peer_table_remember_inbound():
    pt = PeerTable()
    pt.remember_inbound("192.168.1.10", 4440)
    p = pt.lookup_by_endpoint("192.168.1.10:4440")
    assert p is not None
    assert p.via == "inbound"


def test_parse_bootstrap_file_skips_comments_and_blanks(tmp_path: Path):
    p = tmp_path / "bootstrap_peers.txt"
    p.write_text(
        "# header comment\n"
        "\n"
        "  \n"
        "10.0.0.1:4440\n"
        "  10.0.0.2:4440  \n"
        "bad-no-port\n"
        "# trailing comment\n"
        "10.0.0.3:5555\n",
        encoding="utf-8",
    )
    peers = parse_bootstrap_file(p)
    assert peers == ["10.0.0.1:4440", "10.0.0.2:4440", "10.0.0.3:5555"]


def test_parse_bootstrap_file_missing(tmp_path: Path):
    assert parse_bootstrap_file(tmp_path / "does-not-exist") == []


def test_discovered_peer_host_port():
    p = DiscoveredPeer(quic_endpoint="host:1234")
    assert p.host_port() == ("host", 1234)
    q = DiscoveredPeer(quic_endpoint="host")  # bare host, default port
    assert p.host_port() == ("host", 1234)
    # advertiser on a CI machine without a network is flaky.
    a = MdnsAdvertiser(host="127.0.0.1", port=4440, node_public_id="node1abc")
    assert a._host == "127.0.0.1"
    assert a._port == 4440


def test_mdns_browser_construction_does_not_start():
    pt = PeerTable()
    b = MdnsBrowser(pt)
    assert b._table is pt