"""Tests for key rotation CLI commands (rotate-x25519, key-update)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src.narada_identity import cli as cli_module
from src.narada_identity.cli import build_parser
from src.narada_identity.identity import (
    generate_identity,
    identity_from_keystore,
    rotate_identity_preserve_x25519,
)
from src.narada_identity.keystore import InMemoryKeystore


class TestRotateX25519Cli:
    def test_rotate_x25519_basic(self, capsys, monkeypatch):
        keystore = InMemoryKeystore()
        identity, mnemonic = generate_identity("test@example.com", keystore=keystore)
        old_public_id = identity.public_id

        monkeypatch.setattr(cli_module, "_build_keystore", lambda args: keystore)

        parser = build_parser()
        args = parser.parse_args(["--memory", "rotate-x25519", "test@example.com"])
        rc = args.func(args)
        assert rc == 0

        output = capsys.readouterr().out
        assert "Public id:" in output
        assert "X25519 key: preserved" in output
        assert "New recovery mnemonic" in output

        new_identity = identity_from_keystore("test@example.com", keystore)
        assert new_identity.public_id != old_public_id

    def test_rotate_x25519_no_identity(self, capsys, monkeypatch):
        keystore = InMemoryKeystore()
        monkeypatch.setattr(cli_module, "_build_keystore", lambda args: keystore)

        parser = build_parser()
        args = parser.parse_args(["--memory", "rotate-x25519", "nonexistent@example.com"])
        rc = args.func(args)
        assert rc == 1
        assert "nothing to rotate" in capsys.readouterr().err


class TestKeyUpdateCli:
    def test_key_update_requires_old_mnemonic(self, capsys, monkeypatch):
        keystore = InMemoryKeystore()
        identity, mnemonic = generate_identity("test@example.com", keystore=keystore)
        recipient, _ = generate_identity("recipient@example.com", keystore=InMemoryKeystore())

        monkeypatch.setattr(cli_module, "_build_keystore", lambda args: keystore)

        parser = build_parser()
        args = parser.parse_args([
            "--memory",
            "key-update",
            "test@example.com",
            recipient.public_id,
        ])
        rc = args.func(args)
        assert rc == 1
        assert "old-mnemonic is required" in capsys.readouterr().err

    def test_key_update_with_old_mnemonic(self, capsys, monkeypatch):
        keystore = InMemoryKeystore()
        old_identity, old_mnemonic = generate_identity("test@example.com", keystore=keystore)

        new_identity, _ = rotate_identity_preserve_x25519("test@example.com", keystore)

        recipient, _ = generate_identity("recipient@example.com", keystore=InMemoryKeystore())

        monkeypatch.setattr(cli_module, "_build_keystore", lambda args: keystore)

        parser = build_parser()
        args = parser.parse_args([
            "--memory",
            "key-update",
            "test@example.com",
            recipient.public_id,
            "--old-mnemonic",
            old_mnemonic,
        ])
        rc = args.func(args)
        assert rc == 0

        import json
        output = capsys.readouterr().out
        envelope = json.loads(output)
        assert envelope["v"] == 3
        assert envelope["sender_public_id"] == old_identity.public_id
        assert envelope["recipient_public_id"] == recipient.public_id

    def test_key_update_rejects_wrong_mnemonic(self, capsys, monkeypatch):
        keystore = InMemoryKeystore()
        identity, _ = generate_identity("test@example.com", keystore=keystore)
        rotate_identity_preserve_x25519("test@example.com", keystore)

        recipient, _ = generate_identity("recipient@example.com", keystore=InMemoryKeystore())

        monkeypatch.setattr(cli_module, "_build_keystore", lambda args: keystore)

        wrong_mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        parser = build_parser()
        args = parser.parse_args([
            "--memory",
            "key-update",
            "test@example.com",
            recipient.public_id,
            "--old-mnemonic",
            wrong_mnemonic,
        ])
        rc = args.func(args)
        assert rc == 0
