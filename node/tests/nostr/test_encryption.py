"""Tests for NIP-04 and NIP-44 encryption."""

from __future__ import annotations

import base64

import pytest

from src.nostr.encryption import (
    nip04_decrypt,
    nip04_encrypt,
    nip44_decrypt,
    nip44_encrypt,
)
from src.nostr.identity import generate_nostr_identity


class TestNIP04:
    """Tests for NIP-04 (AES-256-CBC)."""

    def test_encrypt_decrypt_roundtrip(self):
        alice = generate_nostr_identity()
        bob = generate_nostr_identity()

        plaintext = "Hello, Bob! This is a secret message."
        encrypted = nip04_encrypt(
            plaintext,
            alice._private_key_bytes,
            bob.x25519_public_key_bytes,
        )
        assert "?iv=" in encrypted

        decrypted = nip04_decrypt(
            encrypted,
            bob._private_key_bytes,
            alice.x25519_public_key_bytes,
        )
        assert decrypted == plaintext

    def test_decrypt_wrong_recipient(self):
        alice = generate_nostr_identity()
        bob = generate_nostr_identity()
        carol = generate_nostr_identity()

        encrypted = nip04_encrypt(
            "secret",
            alice._private_key_bytes,
            bob.x25519_public_key_bytes,
        )
        with pytest.raises(ValueError, match="padding|PKCS7"):
            nip04_decrypt(
                encrypted,
                carol._private_key_bytes,
                alice.x25519_public_key_bytes,
            )

    def test_decrypt_tampered_ciphertext(self):
        alice = generate_nostr_identity()
        bob = generate_nostr_identity()

        encrypted = nip04_encrypt(
            "secret",
            alice._private_key_bytes,
            bob.x25519_public_key_bytes,
        )
        payload, iv_part = encrypted.rsplit("?iv=", 1)
        tampered = payload[:-1] + ("A" if payload[-1] != "A" else "B") + "?iv=" + iv_part

        with pytest.raises(ValueError):
            nip04_decrypt(
                tampered,
                bob._private_key_bytes,
                alice.x25519_public_key_bytes,
            )

    def test_different_plaintexts_produce_different_ciphertexts(self):
        alice = generate_nostr_identity()
        bob = generate_nostr_identity()

        enc1 = nip04_encrypt("msg1", alice._private_key_bytes, bob.x25519_public_key_bytes)
        enc2 = nip04_encrypt("msg2", alice._private_key_bytes, bob.x25519_public_key_bytes)
        assert enc1 != enc2

    def test_same_plaintext_produces_different_ciphertexts(self):
        """Random IV means same plaintext encrypts to different ciphertexts."""
        alice = generate_nostr_identity()
        bob = generate_nostr_identity()

        enc1 = nip04_encrypt("same", alice._private_key_bytes, bob.x25519_public_key_bytes)
        enc2 = nip04_encrypt("same", alice._private_key_bytes, bob.x25519_public_key_bytes)
        assert enc1 != enc2

    def test_empty_plaintext(self):
        alice = generate_nostr_identity()
        bob = generate_nostr_identity()

        encrypted = nip04_encrypt("", alice._private_key_bytes, bob.x25519_public_key_bytes)
        decrypted = nip04_decrypt(encrypted, bob._private_key_bytes, alice.x25519_public_key_bytes)
        assert decrypted == ""

    def test_unicode_plaintext(self):
        alice = generate_nostr_identity()
        bob = generate_nostr_identity()

        plaintext = "Hello 世界! 🌍 ñ ü ö ä"
        encrypted = nip04_encrypt(plaintext, alice._private_key_bytes, bob.x25519_public_key_bytes)
        decrypted = nip04_decrypt(encrypted, bob._private_key_bytes, alice.x25519_public_key_bytes)
        assert decrypted == plaintext

    def test_long_plaintext(self):
        alice = generate_nostr_identity()
        bob = generate_nostr_identity()

        plaintext = "A" * 10000
        encrypted = nip04_encrypt(plaintext, alice._private_key_bytes, bob.x25519_public_key_bytes)
        decrypted = nip04_decrypt(encrypted, bob._private_key_bytes, alice.x25519_public_key_bytes)
        assert decrypted == plaintext

    def test_invalid_format_no_iv(self):
        with pytest.raises(ValueError, match="missing"):
            nip04_decrypt("not-a-valid-format", b"\x00" * 32, b"\x00" * 32)


class TestNIP44:
    """Tests for NIP-44 (ChaCha20-Poly1305)."""

    def test_encrypt_decrypt_roundtrip(self):
        alice = generate_nostr_identity()
        bob = generate_nostr_identity()

        plaintext = "Hello via NIP-44!"
        ciphertext = nip44_encrypt(
            plaintext,
            alice._private_key_bytes,
            bob.x25519_public_key_bytes,
        )
        decrypted = nip44_decrypt(
            ciphertext,
            bob._private_key_bytes,
            alice.x25519_public_key_bytes,
        )
        assert decrypted == plaintext

    def test_decrypt_wrong_recipient(self):
        alice = generate_nostr_identity()
        bob = generate_nostr_identity()
        carol = generate_nostr_identity()

        ciphertext = nip44_encrypt(
            "secret",
            alice._private_key_bytes,
            bob.x25519_public_key_bytes,
        )
        with pytest.raises(Exception):
            nip44_decrypt(
                ciphertext,
                carol._private_key_bytes,
                alice.x25519_public_key_bytes,
            )

    def test_tampered_ciphertext(self):
        alice = generate_nostr_identity()
        bob = generate_nostr_identity()

        ciphertext = nip44_encrypt(
            "secret",
            alice._private_key_bytes,
            bob.x25519_public_key_bytes,
        )
        tampered = bytearray(ciphertext)
        tampered[-1] ^= 0xFF
        with pytest.raises(Exception):
            nip44_decrypt(
                bytes(tampered),
                bob._private_key_bytes,
                alice.x25519_public_key_bytes,
            )

    def test_different_plaintexts(self):
        alice = generate_nostr_identity()
        bob = generate_nostr_identity()

        ct1 = nip44_encrypt("one", alice._private_key_bytes, bob.x25519_public_key_bytes)
        ct2 = nip44_encrypt("two", alice._private_key_bytes, bob.x25519_public_key_bytes)
        assert ct1 != ct2

    def test_unicode(self):
        alice = generate_nostr_identity()
        bob = generate_nostr_identity()

        plaintext = "你好世界 🌍"
        ct = nip44_encrypt(plaintext, alice._private_key_bytes, bob.x25519_public_key_bytes)
        pt = nip44_decrypt(ct, bob._private_key_bytes, alice.x25519_public_key_bytes)
        assert pt == plaintext

    def test_ciphertext_too_short(self):
        alice = generate_nostr_identity()
        bob = generate_nostr_identity()
        with pytest.raises(ValueError, match="too short"):
            nip44_decrypt(b"\x00" * 5, alice._private_key_bytes, bob.x25519_public_key_bytes)


class TestCrossProtocol:
    """Tests ensuring NIP-04 and NIP-44 produce different outputs."""

    def test_nip04_and_nip44_different_formats(self):
        alice = generate_nostr_identity()
        bob = generate_nostr_identity()

        nip04_result = nip04_encrypt("secret", alice._private_key_bytes, bob.x25519_public_key_bytes)
        nip44_result = nip44_encrypt("secret", alice._private_key_bytes, bob.x25519_public_key_bytes)
        # NIP-04 returns a string with ?iv=, NIP-44 returns raw bytes
        assert isinstance(nip04_result, str)
        assert isinstance(nip44_result, bytes)
        assert "?iv=" in nip04_result
