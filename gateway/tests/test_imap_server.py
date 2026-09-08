"""Tests for :mod:`gateway.gateway.imap_server`."""

from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

import pytest

from gateway.gateway.imap_server import NaradaImapServer, _parse_seq_set, _record_to_rfc822


@pytest.fixture
def mailbox_dir(tmp_path: Path) -> Path:
    """Create a temporary mailbox directory with sample records."""
    etc = tmp_path / "etc"
    etc.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "uid": "msg-1",
            "source": "narada",
            "sender": "alice@example.com",
            "to": ["bob@example.com"],
            "cc": [],
            "date": "1735689600",
            "subject": "Hello",
            "body": "Hi Bob",
            "flags": ["\\Seen"],
            "message_id": "<msg-1@test>",
        },
        {
            "uid": "msg-2",
            "source": "narada",
            "sender": "carol@example.com",
            "to": ["bob@example.com"],
            "cc": ["dave@example.com"],
            "date": "1735776000",
            "subject": "Meeting",
            "body": "Let's meet tomorrow",
            "flags": [],
            "message_id": "<msg-2@test>",
        },
    ]
    path = etc / "mailbox.bob_example_com.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
    return tmp_path


@pytest.fixture
def server(mailbox_dir: Path) -> NaradaImapServer:
    s = NaradaImapServer(data_dir=mailbox_dir, account_id="bob@example.com", port=0)
    yield s
    s.shutdown()


def _send_imap_cmd(
    host: str, port: int, tag: str, command: str
) -> str:
    """Send a single IMAP command and return the full response."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    try:
        sock.connect((host, port))
        # Read greeting.
        sock.recv(4096)
        # Send command.
        sock.sendall(f"{tag} {command}\r\n".encode())
        time.sleep(0.1)
        response = b""
        while True:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
                # Check for tagged response.
                decoded = response.decode("utf-8", errors="replace")
                if f"{tag} " in decoded:
                    break
            except socket.timeout:
                break
        return response.decode("utf-8", errors="replace")
    finally:
        sock.close()


class TestNaradaImapServer:
    def test_starts_and_stops(self, server: NaradaImapServer):
        # Use a dynamic port by binding first.
        server._port = 0
        server._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server._server_socket.bind(("127.0.0.1", 0))
        server._server_socket.listen(5)
        port = server._server_socket.getsockname()[1]
        server._port = port
        server._running = True
        server._thread = threading.Thread(
            target=server._serve, daemon=True
        )
        server._thread.start()
        time.sleep(0.2)
        assert server.is_running
        server.shutdown()
        assert not server.is_running

    def test_capability(self, server: NaradaImapServer):
        server._port = 0
        server._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server._server_socket.bind(("127.0.0.1", 0))
        server._server_socket.listen(5)
        port = server._server_socket.getsockname()[1]
        server._port = port
        server._running = True
        server._thread = threading.Thread(target=server._serve, daemon=True)
        server._thread.start()
        time.sleep(0.2)
        try:
            resp = _send_imap_cmd("127.0.0.1", port, "A1", "CAPABILITY")
            assert "CAPABILITY" in resp
            assert "IMAP4rev1" in resp
        finally:
            server.shutdown()


class TestParseSeqSet:
    def test_single(self):
        assert _parse_seq_set("1", 5) == [0]

    def test_range(self):
        assert _parse_seq_set("2:4", 5) == [1, 2, 3]

    def test_star(self):
        assert _parse_seq_set("3:*", 5) == [2, 3, 4]

    def test_comma(self):
        assert _parse_seq_set("1,3,5", 5) == [0, 2, 4]

    def test_out_of_range(self):
        assert _parse_seq_set("10", 5) == []


class TestRecordToRfc822:
    def test_basic(self):
        rec = {
            "subject": "Test",
            "sender": "alice@example.com",
            "to": ["bob@example.com"],
            "cc": [],
            "date": "1735689600",
            "body": "Hello",
            "message_id": "<test@test>",
        }
        msg = _record_to_rfc822(rec)
        assert msg["Subject"] == "Test"
        assert msg["From"] == "alice@example.com"
        assert msg["To"] == "bob@example.com"
        assert "Hello" in msg.get_content()

    def test_string_to_field(self):
        rec = {
            "subject": "Test",
            "sender": "alice@example.com",
            "to": "bob@example.com",
            "date": "1735689600",
            "body": "Hello",
        }
        msg = _record_to_rfc822(rec)
        assert msg["To"] == "bob@example.com"
