"""Errors raised by the Lattice identity layer."""


class LatticeIdentityError(Exception):
    """Base class for identity-layer errors."""


class LatticeKeystoreError(LatticeIdentityError):
    """Raised by the keystore when keys cannot be stored or loaded."""


class LatticeMnemonicError(LatticeIdentityError):
    """Raised when a BIP-39 mnemonic is invalid or cannot be generated."""


__all__ = [
    "LatticeIdentityError",
    "LatticeKeystoreError",
    "LatticeMnemonicError",
]
