"""Top-level narada identity: keypair + public id + sign/verify/encrypt."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .encoding import encode_public_id, decode_public_id
from .errors import NaradaIdentityError
from .keypair import Keypair, keypair_from_seed, verify_signature
from .keystore import NaradaKeystore
from .mnemonic import generate_mnemonic, mnemonic_to_seed


@dataclass
class NaradaIdentity:
    """A loaded Narada identity: keypair + public id.

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
        public id (``narada1...``). Returns the raw X25519 ECDH output;
        callers should run it through a KDF (HKDF) before using it as a
        symmetric key.
        """
        _version, _ed_pub, x_pub = decode_public_id(peer_public_id)
        return self.keypair.shared_secret_with(x_pub)

    @classmethod
    def from_keypair(cls, account_id: str, keypair: Keypair) -> "NaradaIdentity":
        public_id = encode_public_id(
            keypair.ed25519_public_bytes,
            keypair.x25519_public_bytes,
        )
        return cls(account_id=account_id, keypair=keypair, public_id=public_id)


def generate_identity(
    account_id: str,
    keystore: Optional[NaradaKeystore] = None,
) -> tuple["NaradaIdentity", str]:
    """Generate a new identity, optionally persisting it in ``keystore``.

    Returns the loaded :class:`NaradaIdentity` and a 12-word recovery
    mnemonic. The mnemonic is the only durable backup of the private
    material if no keystore is provided.
    """
    mnemonic = generate_mnemonic()
    seed = mnemonic_to_seed(mnemonic)
    keypair = keypair_from_seed(seed)
    if keystore is not None:
        keystore.store(account_id, seed)
    return NaradaIdentity.from_keypair(account_id, keypair), mnemonic


def identity_from_mnemonic(
    account_id: str,
    mnemonic: str,
    keystore: Optional[NaradaKeystore] = None,
) -> "NaradaIdentity":
    """Recover an identity from a 12-word BIP-39 mnemonic."""
    seed = mnemonic_to_seed(mnemonic)
    keypair = keypair_from_seed(seed)
    if keystore is not None:
        keystore.store(account_id, seed)
    return NaradaIdentity.from_keypair(account_id, keypair)


def identity_from_keystore(
    account_id: str,
    keystore: NaradaKeystore,
) -> "NaradaIdentity":
    """Load an identity previously stored in ``keystore``."""
    seed = keystore.load(account_id)
    return NaradaIdentity.from_keypair(account_id, keypair_from_seed(seed))


def rotate_identity(
    account_id: str,
    keystore: NaradaKeystore,
) -> tuple["NaradaIdentity", str]:
    """Replace the stored seed with a fresh one. Returns the new identity
    and its mnemonic.

    Raises :class:`NaradaIdentityError` if no identity is currently
    stored for ``account_id``; rotation without an existing identity is
    just :func:`generate_identity` with a keystore.
    """
    if not keystore.has(account_id):
        raise NaradaIdentityError(
            f"No identity stored for account_id={account_id!r}; nothing to rotate"
        )
    mnemonic = generate_mnemonic()
    seed = mnemonic_to_seed(mnemonic)
    keypair = keypair_from_seed(seed)
    keystore.store(account_id, seed)
    return NaradaIdentity.from_keypair(account_id, keypair), mnemonic


def rotate_identity_preserve_x25519(
    account_id: str,
    keystore: NaradaKeystore,
) -> tuple["NaradaIdentity", str]:
    """Rotate the Ed25519 signing key while preserving the X25519 encryption key.

    Returns ``(new_identity, new_mnemonic)`` with a fresh BIP-39
    mnemonic but the same X25519 public key as the prior identity.

    The X25519 *private* key is preserved across the rotation so
    the new identity can decrypt envelopes sealed to the prior
    one (Option A in the design discussion). The X25519 private
    key is stored in the keystore's secret-blob slot via
    :meth:`store_secret`; on load, the new identity rebuilds
    the keypair from the new Ed25519 seed plus the preserved
    X25519 private key.

    Raises :class:`NaradaIdentityError` if no identity is
    currently stored for ``account_id``.
    """
    if not keystore.has(account_id):
        raise NaradaIdentityError(
            f"No identity stored for account_id={account_id!r}; nothing to rotate"
        )
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
    )

    from .keypair import keypair_with_x25519_preserved

    prior_identity = identity_from_keystore_with_preserved_x25519(
        account_id, keystore
    )
    prior_x25519_private = prior_identity.keypair.x25519_private.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )
    prior_x25519_public = prior_identity.keypair.x25519_public_bytes

    new_mnemonic = generate_mnemonic()
    new_seed = mnemonic_to_seed(new_mnemonic)
    new_keypair = keypair_with_x25519_preserved(
        new_ed25519_seed=new_seed,
        prior_x25519_public_bytes=prior_x25519_public,
        prior_x25519_private_bytes=prior_x25519_private,
    )
    keystore.store(account_id, new_seed)
    keystore.store_secret(account_id, prior_x25519_private)
    return NaradaIdentity.from_keypair(account_id, new_keypair), new_mnemonic

def identity_from_keystore_with_preserved_x25519(
    account_id: str,
    keystore: NaradaKeystore,
) -> "NaradaIdentity":
    """Load an identity, restoring the X25519 private key if it was preserved.

    Used after :func:`rotate_identity_preserve_x25519`. The
    new identity's X25519 key is rebuilt from the preserved
    X25519 private key (stored in the secret-blob slot) and
    the new Ed25519 seed (stored in the regular slot). If no
    secret blob exists, the X25519 key is derived from the new
    seed via HKDF (the standard path, used for non-Option-A
    identities).
    """
    seed = keystore.load(account_id)
    if keystore.has_secret(account_id):
        from .keypair import keypair_with_x25519_preserved

        prior_x25519_private = keystore.load_secret(account_id)
        from cryptography.hazmat.primitives.asymmetric.x25519 import (
            X25519PrivateKey,
        )
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            PublicFormat,
        )

        x_priv = X25519PrivateKey.from_private_bytes(prior_x25519_private)
        prior_x25519_public = x_priv.public_key().public_bytes(
            encoding=Encoding.Raw,
            format=PublicFormat.Raw,
        )
        keypair = keypair_with_x25519_preserved(
            new_ed25519_seed=seed,
            prior_x25519_public_bytes=prior_x25519_public,
            prior_x25519_private_bytes=prior_x25519_private,
        )
        return NaradaIdentity.from_keypair(account_id, keypair)
    return identity_from_keystore(account_id, keystore)
def verify_public_id_signature(
    public_id: str,
    signature: bytes,
    data: bytes,
) -> bool:
    """Verify a signature against a public id."""
    _version, ed_pub, _x_pub = decode_public_id(public_id)
    return verify_signature(ed_pub, signature, data)


__all__ = [
    "NaradaIdentity",
    "generate_identity",
    "identity_from_keystore",
    "identity_from_mnemonic",
    "rotate_identity",
    "rotate_identity_preserve_x25519",
    "verify_public_id_signature",
]
