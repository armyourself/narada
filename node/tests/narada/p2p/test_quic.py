"""Tests for the QUIC transport + endpoint parser."""

from __future__ import annotations

import pytest

from src.narada.p2p.quic import (
    _DEFAULT_QUIC_PORT,
    _MAX_FRAME_BYTES,
    QuicPeerError,
    parse_quic_endpoint,
)
from src.narada.p2p.tls import _NARADA_ALPN, fingerprint_pem, load_or_create
from src.narada.transport import NaradaTransportError


def test_parse_quic_endpoint_with_scheme():
    assert parse_quic_endpoint("quic://host:5000") == ("host", 5000)


def test_parse_quic_endpoint_with_narada_scheme():
    assert parse_quic_endpoint("narada://x:9000") == ("x", 9000)


def test_parse_quic_endpoint_bare_host_uses_default_port():
    assert parse_quic_endpoint("node.example.com") == ("node.example.com", _DEFAULT_QUIC_PORT)


def test_parse_quic_endpoint_host_and_port():
    assert parse_quic_endpoint("10.0.0.5:12345") == ("10.0.0.5", 12345)


def test_parse_quic_endpoint_rejects_empty():
    with pytest.raises(QuicPeerError):
        parse_quic_endpoint("")


def test_parse_quic_endpoint_rejects_bad_port():
    with pytest.raises(QuicPeerError):
        parse_quic_endpoint("host:not-a-port")


def test_tls_load_or_create_is_persistent(tmp_path):
    m1 = load_or_create(tmp_path, common_name="n1")
    m2 = load_or_create(tmp_path, common_name="n1")
    assert m1.cert_pem == m2.cert_pem


def test_tls_load_or_create_different_dirs_different_certs(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    m1 = load_or_create(a, common_name="node")
    m2 = load_or_create(b, common_name="node")
    assert m1.cert_pem != m2.cert_pem


def test_tls_alpn_is_narada():
    assert _NARADA_ALPN == b"narada/1"


def test_fingerprint_is_stable():
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as t:
        m = load_or_create(pathlib.Path(t), common_name="n")
        fp1 = fingerprint_pem(m.cert_pem)
        fp2 = fingerprint_pem(m.cert_pem)
        assert fp1 == fp2
        assert len(fp1) == 64


def test_transport_send_raises_on_unreachable(tmp_path):
    from src.narada.p2p.quic import QuicNaradaTransport
    tls = load_or_create(tmp_path)
    t = QuicNaradaTransport(tls, timeout_seconds=1.0)
    with pytest.raises(NaradaTransportError):
        t.send("127.0.0.1:1", {"x": 1})


def test_max_frame_bytes_constant_sanity():
    assert _MAX_FRAME_BYTES >= 32 * 1024
    assert _MAX_FRAME_BYTES <= 1024 * 1024