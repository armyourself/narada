"""BIP-39 mnemonic support for Lattice identity recovery.

The 12-word mnemonic encodes a 32-byte Ed25519 seed (16 bytes of entropy
plus a 1-byte checksum, expanded to 32 bytes by hashing). The expansion
is deterministic: same mnemonic -> same seed -> same keypair.

We use the ``mnemonic`` package (``bip-english`` wordlist under the hood)
to generate and validate standard BIP-39 mnemonics, then apply our own
seed-derivation step to reach 32 bytes (BIP-39 normally derives 64 bytes
for BIP-32, but we only need a 32-byte Ed25519 seed).
"""

from __future__ import annotations

import hashlib

from mnemonic import Mnemonic

from .errors import LatticeMnemonicError

_ENTROPY_BITS = 128  # 12 words
_SEED_LEN = 32

_mnemo = Mnemonic("english")


def generate_mnemonic(strength_bits: int = _ENTROPY_BITS) -> str:
    """Generate a new BIP-39 mnemonic.

    Default strength is 128 bits (12 words), which is what we use to
    derive a 32-byte Ed25519 seed.
    """
    if strength_bits != _ENTROPY_BITS:
        raise LatticeMnemonicError(
            f"Lattice identities only support {_ENTROPY_BITS}-bit mnemonics "
            f"(12 words); got strength_bits={strength_bits}"
        )
    return _mnemo.generate(strength=strength_bits)


def validate_mnemonic(phrase: str) -> bool:
    """Return True if ``phrase`` is a valid BIP-39 mnemonic."""
    return _mnemo.check(phrase)


def mnemonic_to_seed(phrase: str) -> bytes:
    """Convert a BIP-39 mnemonic to the 32-byte Lattice Ed25519 seed.

    We do not use BIP-39's ``to_seed`` (PBKDF2 -> 64 bytes for BIP-32);
    instead we hash the mnemonic's entropy (16 bytes from 12 words) to
    32 bytes with SHA-256. This is the secret that gets stored in the
    keystore.
    """
    if not validate_mnemonic(phrase):
        raise LatticeMnemonicError("Invalid BIP-39 mnemonic")
    entropy = _mnemo.to_entropy(phrase)
    if isinstance(entropy, str):
        entropy = entropy.encode("utf-8")
    if len(entropy) != _ENTROPY_BITS // 8:
        raise LatticeMnemonicError(
            f"Unexpected entropy length from mnemonic: {len(entropy)}"
        )
    return hashlib.sha256(entropy).digest()


__all__ = [
    "generate_mnemonic",
    "mnemonic_to_seed",
    "validate_mnemonic",
]
