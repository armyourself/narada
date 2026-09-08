"""Narada identity package.

The Narada identity layer gives each Narada account a cryptographic
identity consisting of an Ed25519 signing key and an X25519 encryption
key, with a public-id string formatted as ``narada1...`` (bech32m).

This package is the implementation of Phase 1 of the Narada roadmap. The
transport layer (Phase 2+) will use these identities; the on-the-wire
message format and node-to-node transport are intentionally out of scope
here.

See ``protocol/identity.md`` for the spec.
"""

from .encoding import (
    IdentityVersion,
    decode_public_id,
    encode_public_id,
    is_valid_public_id,
)
from .errors import NaradaIdentityError, NaradaKeystoreError, NaradaMnemonicError
from .identity import (
    NaradaIdentity,
    generate_identity,
    identity_from_keystore,
    identity_from_mnemonic,
    rotate_identity,
    rotate_identity_preserve_x25519,
)
from .keypair import (
    Keypair,
    generate_keypair,
    keypair_from_seed,
    verify_signature,
)
from .keystore import (
    InMemoryKeystore,
    KeyringKeystore,
    NaradaKeystore,
    PassphraseKeystore,
)
from .mnemonic import generate_mnemonic, mnemonic_to_seed, validate_mnemonic

__all__ = [
    "IdentityVersion",
    "InMemoryKeystore",
    "Keypair",
    "KeyringKeystore",
    "NaradaIdentity",
    "NaradaIdentityError",
    "NaradaKeystore",
    "NaradaKeystoreError",
    "NaradaMnemonicError",
    "PassphraseKeystore",
    "decode_public_id",
    "encode_public_id",
    "generate_identity",
    "generate_keypair",
    "identity_from_keystore",
    "identity_from_mnemonic",
    "is_valid_public_id",
    "keypair_from_seed",
    "mnemonic_to_seed",
    "rotate_identity",
    "rotate_identity_preserve_x25519",
    "validate_mnemonic",
    "verify_signature",
]
