"""Lattice identity package.

The Lattice identity layer gives each Lattice account a cryptographic
identity consisting of an Ed25519 signing key and an X25519 encryption
key, with a public-id string formatted as ``lattice1...`` (bech32m).

This package is the implementation of Phase 1 of the Lattice roadmap. The
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
from .errors import LatticeIdentityError, LatticeKeystoreError, LatticeMnemonicError
from .identity import LatticeIdentity, generate_identity, identity_from_mnemonic
from .keypair import (
    Keypair,
    generate_keypair,
    keypair_from_seed,
)
from .keystore import (
    InMemoryKeystore,
    KeyringKeystore,
    LatticeKeystore,
    PassphraseKeystore,
)
from .mnemonic import generate_mnemonic, mnemonic_to_seed, validate_mnemonic

__all__ = [
    "IdentityVersion",
    "InMemoryKeystore",
    "Keypair",
    "KeyringKeystore",
    "LatticeIdentity",
    "LatticeIdentityError",
    "LatticeKeystore",
    "LatticeKeystoreError",
    "LatticeMnemonicError",
    "PassphraseKeystore",
    "decode_public_id",
    "encode_public_id",
    "generate_identity",
    "generate_keypair",
    "generate_mnemonic",
    "identity_from_mnemonic",
    "is_valid_public_id",
    "keypair_from_seed",
    "mnemonic_to_seed",
    "validate_mnemonic",
]
