"""NIP-04 encrypted direct messages.

NIP-04 defines a simple encrypted direct message scheme using
AES-256-CBC with PKCS7 padding. The shared secret is derived via
X25519 ECDH.

In Nostr, users have Ed25519 keys. NIP-04 requires X25519 ECDH.
The conversion Ed25519→X25519 is done via the cryptography library's
``Ed25519PrivateKey.x25519()`` method, which derives the X25519
private key from the Ed25519 key's scalar.

Message format (NIP-04):

    base64(ciphertext) + "?iv=" + base64(iv)
"""

from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PublicKey,
    X25519PrivateKey,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives import padding as sym_padding


def _ed25519_to_x25519_private(ed25519_seed_bytes: bytes) -> X25519PrivateKey:
    """Convert an Ed25519 seed (32 bytes) to an X25519 private key.

    The standard NIP-04 conversion:
    1. SHA-512 hash the Ed25519 seed
    2. Take the first 32 bytes as the scalar
    3. Clamp the scalar for X25519
    4. Use as X25519 private key
    """
    import hashlib
    raw_scalar = hashlib.sha512(ed25519_seed_bytes).digest()[:32]
    # Clamp for X25519 (Curve25519 scalar clamping)
    scalar = bytearray(raw_scalar)
    scalar[0] &= 248   # Clear bits 0, 1, 2
    scalar[31] &= 127  # Clear bit 255
    scalar[31] |= 64   # Set bit 254
    return X25519PrivateKey.from_private_bytes(bytes(scalar))


def _x25519_public_from_ed25519(ed25519_seed_bytes: bytes) -> bytes:
    """Get the X25519 public key bytes from an Ed25519 seed."""
    x25519_priv = _ed25519_to_x25519_private(ed25519_seed_bytes)
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    return x25519_priv.public_key().public_bytes(
        encoding=Encoding.Raw, format=PublicFormat.Raw
    )


def _nip04_shared_secret(
    private_key_bytes: bytes,
    public_key_bytes: bytes,
) -> bytes:
    """Derive a NIP-04 shared secret via X25519 ECDH.

    ``private_key_bytes`` is an Ed25519 seed (32 bytes).
    ``public_key_bytes`` is an X25519 public key (32 bytes).
    """
    x25519_priv = _ed25519_to_x25519_private(private_key_bytes)
    x25519_pub = X25519PublicKey.from_public_bytes(public_key_bytes)
    return x25519_priv.exchange(x25519_pub)


def nip04_encrypt(
    plaintext: str,
    sender_ed25519_private_bytes: bytes,
    recipient_x25519_public_bytes: bytes,
) -> str:
    """Encrypt a message using NIP-04 (AES-256-CBC).

    Parameters
    ----------
    plaintext:
        The message to encrypt.
    sender_ed25519_private_bytes:
        Sender's Ed25519 seed (32 bytes).
    recipient_x25519_public_bytes:
        Recipient's X25519 public key (32 bytes).
    """
    shared_secret = _nip04_shared_secret(sender_ed25519_private_bytes, recipient_x25519_public_bytes)
    aes_key = hashlib.sha256(shared_secret).digest()

    iv = secrets.token_bytes(16)

    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()

    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    return (
        base64.b64encode(ciphertext).decode("ascii")
        + "?iv="
        + base64.b64encode(iv).decode("ascii")
    )


def nip04_decrypt(
    encrypted: str,
    recipient_ed25519_private_bytes: bytes,
    sender_x25519_public_bytes: bytes,
) -> str:
    """Decrypt a NIP-04 encrypted message.

    Parameters
    ----------
    encrypted:
        The NIP-04 encrypted string: ``base64(ciphertext)?iv=base64(iv)``
    recipient_ed25519_private_bytes:
        Recipient's Ed25519 seed (32 bytes).
    sender_x25519_public_bytes:
        Sender's X25519 public key (32 bytes).

    Raises
    ------
    ValueError
        If the message is malformed or decryption fails.
    """
    if "?iv=" not in encrypted:
        raise ValueError("Invalid NIP-04 format: missing ?iv= separator")

    payload_b64, iv_b64 = encrypted.rsplit("?iv=", 1)
    ciphertext = base64.b64decode(payload_b64)
    iv = base64.b64decode(iv_b64)

    if len(iv) != 16:
        raise ValueError(f"Invalid IV length: expected 16, got {len(iv)}")

    shared_secret = _nip04_shared_secret(recipient_ed25519_private_bytes, sender_x25519_public_bytes)
    aes_key = hashlib.sha256(shared_secret).digest()

    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()

    unpadder = sym_padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded) + unpadder.finalize()

    return plaintext.decode("utf-8")


def nip44_encrypt(
    plaintext: str,
    sender_ed25519_private_bytes: bytes,
    recipient_x25519_public_bytes: bytes,
) -> bytes:
    """Encrypt a message using NIP-44-style ChaCha20-Poly1305.

    More secure than NIP-04 (AEAD vs CBC). Used for
    Narada-to-Narada communication over Nostr relays.

    Returns the raw ciphertext bytes (nonce || encrypted_data_with_tag).
    """
    shared_secret = _nip04_shared_secret(sender_ed25519_private_bytes, recipient_x25519_public_bytes)
    key = hashlib.sha256(shared_secret).digest()

    nonce = secrets.token_bytes(12)

    aead = ChaCha20Poly1305(key)
    ciphertext = aead.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)

    return nonce + ciphertext


def nip44_decrypt(
    ciphertext: bytes,
    recipient_ed25519_private_bytes: bytes,
    sender_x25519_public_bytes: bytes,
) -> str:
    """Decrypt a NIP-44-style encrypted message.

    Parameters
    ----------
    ciphertext:
        The raw ciphertext bytes (nonce || encrypted_data_with_tag).
    recipient_ed25519_private_bytes:
        Recipient's Ed25519 seed (32 bytes).
    sender_x25519_public_bytes:
        Sender's X25519 public key (32 bytes).
    """
    shared_secret = _nip04_shared_secret(recipient_ed25519_private_bytes, sender_x25519_public_bytes)
    key = hashlib.sha256(shared_secret).digest()

    if len(ciphertext) < 12:
        raise ValueError("Ciphertext too short")

    nonce = ciphertext[:12]
    encrypted = ciphertext[12:]

    aead = ChaCha20Poly1305(key)
    plaintext = aead.decrypt(nonce, encrypted, associated_data=None)
    return plaintext.decode("utf-8")


__all__ = [
    "nip04_decrypt",
    "nip04_encrypt",
    "nip44_decrypt",
    "nip44_encrypt",
    "_x25519_public_from_ed25519",
]
