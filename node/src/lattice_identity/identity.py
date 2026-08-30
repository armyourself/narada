"""Top-level Lattice identity: keypair + public id + sign/verify/encrypt."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .encoding import encode_public_id, decode_public_id
from .errors import LatticeIdentityError
from .keypair import Keypair, keypair_from_seed, verify_signature
from .keystore import LatticeKeystore
from .mnemonic import generate_mnemonic, mnemonic_to_seed


@dataclass
class LatticeIdentity:
    """A loaded Lattice identity: keypair + public id.

    Use :func:`generate_identity` to create a new one, or
    :func:`identity_from_mnemonic` to recover one from a 12-word phrase.
    """

    account_id: str
    keypair: Keypair
    public_id: str

    def sign(self, data: bytes) -> bytes:
        return self.keypair.sign(data)

    def shared_secret_with(self, peer_public_id: str) -> bytes:
        """Derive a 32-byte shared secret with a peer identified by their
        public id (``lattice1...``). Returns the raw X25519 ECDH output;
        callers should run it through a KDF (HKDF) before using it as a
        symmetric key.
        """
        _version, _ed_pub, x_pub = decode_public_id(peer_public_id)
        return self.keypair.shared_secret_with(x_pub)

    @classmethod
    def from_keypair(cls, account_id: str, keypair: Keypair) -> "LatticeIdentity":
        public_id = encode_public_id(
            keypair.ed25519_public_bytes,
            keypair.x25519_public_bytes,
        )
        return cls(account_id=account_id, keypair=keypair, public_id=public_id)


def generate_identity(
    account_id: str,
    keystore: Optional[LatticeKeystore] = None,
) -> tuple["LatticeIdentity", str]:
    """Generate a new identity, optionally persisting it in ``keystore``.

    Returns the loaded :class:`LatticeIdentity` and a 12-word recovery
    mnemonic. The mnemonic is the only durable backup of the private
    material if no keystore is provided.
    """
    mnemonic = generate_mnemonic()
    seed = mnemonic_to_seed(mnemonic)
    keypair = keypair_from_seed(seed)
    if keystore is not None:
        keystore.store(account_id, seed)
    return LatticeIdentity.from_keypair(account_id, keypair), mnemonic


def identity_from_mnemonic(
    account_id: str,
    mnemonic: str,
    keystore: Optional[LatticeKeystore] = None,
) -> "LatticeIdentity":
    """Recover an identity from a 12-word BIP-39 mnemonic."""
    seed = mnemonic_to_seed(mnemonic)
    keypair = keypair_from_seed(seed)
    if keystore is not None:
        keystore.store(account_id, seed)
    return LatticeIdentity.from_keypair(account_id, keypair)


def identity_from_keystore(
    account_id: str,
    keystore: LatticeKeystore,
) -> "LatticeIdentity":
    """Load an identity previously stored in ``keystore``."""
    seed = keystore.load(account_id)
    return LatticeIdentity.from_keypair(account_id, keypair_from_seed(seed))


def rotate_identity(
    account_id: str,
    keystore: LatticeKeystore,
) -> tuple["LatticeIdentity", str]:
    """Replace the stored seed with a fresh one. Returns the new identity
    and its mnemonic.

    Raises :class:`LatticeIdentityError` if no identity is currently
    stored for ``account_id``; rotation without an existing identity is
    just :func:`generate_identity` with a keystore.
    """
    if not keystore.has(account_id):
        raise LatticeIdentityError(
            f"No identity stored for account_id={account_id!r}; nothing to rotate"
        )
    mnemonic = generate_mnemonic()
    seed = mnemonic_to_seed(mnemonic)
    keypair = keypair_from_seed(seed)
    keystore.store(account_id, seed)
    return LatticeIdentity.from_keypair(account_id, keypair), mnemonic


def verify_public_id_signature(
    public_id: str,
    signature: bytes,
    data: bytes,
) -> bool:
    """Verify a signature against a public id."""
    _version, ed_pub, _x_pub = decode_public_id(public_id)
    return verify_signature(ed_pub, signature, data)


__all__ = [
    "LatticeIdentity",
    "generate_identity",
    "identity_from_keystore",
    "identity_from_mnemonic",
    "rotate_identity",
    "verify_public_id_signature",
]
