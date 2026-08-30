"""Keypair generation and operations for Lattice identities.

A Lattice keypair bundles:

* An Ed25519 signing keypair (used to sign messages and the user's
  on-the-wire identity assertions).
* An X25519 encryption keypair (used to derive shared secrets with
  recipients via ECDH).

The X25519 keypair is deterministically derived from the Ed25519 seed
via HKDF, so a single 32-byte seed is enough to recover both halves.
That keeps the BIP-39 mnemonic small (12 words encode 16 bytes of
entropy plus checksum) while still giving us a strong encryption key.
"""

from __future__ import annotations

from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from .errors import LatticeIdentityError

X25519_INFO = b"lattice-x25519-from-ed25519-seed"
SEED_LEN = 32


def _hkdf_x25519_seed(ed25519_seed: bytes) -> bytes:
    """Deterministically derive an X25519 private key from an Ed25519 seed."""
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=X25519_INFO,
    ).derive(ed25519_seed)
    return derived


@dataclass
class Keypair:
    """A Lattice keypair (Ed25519 + X25519)."""

    ed25519_private: Ed25519PrivateKey
    ed25519_public: Ed25519PublicKey
    x25519_private: X25519PrivateKey
    x25519_public: X25519PublicKey

    @property
    def ed25519_public_bytes(self) -> bytes:
        return self.ed25519_public.public_bytes(
            encoding=Encoding.Raw,
            format=PublicFormat.Raw,
        )

    @property
    def x25519_public_bytes(self) -> bytes:
        return self.x25519_public.public_bytes(
            encoding=Encoding.Raw,
            format=PublicFormat.Raw,
        )

    @property
    def ed25519_seed(self) -> bytes:
        """Return the raw 32-byte Ed25519 seed.

        This is the secret material that gets stored in the keystore and
        encoded into the BIP-39 mnemonic for recovery.
        """
        return self.ed25519_private.private_bytes(
            encoding=Encoding.Raw,
            format=PrivateFormat.Raw,
            encryption_algorithm=NoEncryption(),
        )

    def sign(self, data: bytes) -> bytes:
        return self.ed25519_private.sign(data)

    def shared_secret_with(self, peer_x25519_public_bytes: bytes) -> bytes:
        if len(peer_x25519_public_bytes) != 32:
            raise LatticeIdentityError(
                f"X25519 public key must be 32 bytes, got {len(peer_x25519_public_bytes)}"
            )
        try:
            peer = X25519PublicKey.from_public_bytes(peer_x25519_public_bytes)
            return self.x25519_private.exchange(peer)
        except (ValueError, TypeError) as exc:
            # cryptography raises ValueError on small-subgroup /
            # invalid-curve points. Surface as a typed Lattice error
            # so callers (including the HTTP router) get a 4xx, not a
            # 500 stack trace.
            raise LatticeIdentityError(
                "Invalid X25519 public key"
            ) from exc

    def public_bytes(self) -> bytes:
        """Return the raw public-key bytes (32 + 32 = 64 bytes)."""
        return self.ed25519_public_bytes + self.x25519_public_bytes


def generate_keypair() -> Keypair:
    """Generate a fresh, random Lattice keypair."""
    ed = Ed25519PrivateKey.generate()
    # Use the private key directly; no need to round-trip through
    # private_bytes() + keypair_from_seed().
    ed_pub = ed.public_key()
    seed = ed.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )
    x_seed = _hkdf_x25519_seed(seed)
    x_priv = X25519PrivateKey.from_private_bytes(x_seed)
    x_pub = x_priv.public_key()
    return Keypair(
        ed25519_private=ed,
        ed25519_public=ed_pub,
        x25519_private=x_priv,
        x25519_public=x_pub,
    )


def keypair_from_seed(seed: bytes) -> Keypair:
    """Build a Lattice keypair from a 32-byte Ed25519 seed.

    The X25519 keypair is derived deterministically via HKDF.
    """
    if len(seed) != SEED_LEN:
        raise LatticeIdentityError(
            f"Ed25519 seed must be {SEED_LEN} bytes, got {len(seed)}"
        )
    ed_priv = Ed25519PrivateKey.from_private_bytes(seed)
    ed_pub = ed_priv.public_key()

    x_seed = _hkdf_x25519_seed(seed)
    x_priv = X25519PrivateKey.from_private_bytes(x_seed)
    x_pub = x_priv.public_key()

    return Keypair(
        ed25519_private=ed_priv,
        ed25519_public=ed_pub,
        x25519_private=x_priv,
        x25519_public=x_pub,
    )


def verify_signature(
    public_key_bytes: bytes,
    signature: bytes,
    data: bytes,
) -> bool:
    """Verify an Ed25519 signature against a 32-byte public key."""
    if len(public_key_bytes) != 32:
        raise LatticeIdentityError(
            f"Ed25519 public key must be 32 bytes, got {len(public_key_bytes)}"
        )
    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(signature, data)
        return True
    except InvalidSignature:
        return False
    except (ValueError, TypeError) as exc:
        # Malformed public key bytes -> treat as signature failure, not
        # a crash. Real callers should not pass invalid keys; this is
        # belt-and-suspenders.
        raise LatticeIdentityError("Invalid Ed25519 public key") from exc


__all__ = [
    "Keypair",
    "generate_keypair",
    "keypair_from_seed",
    "verify_signature",
    "SEED_LEN",
]
