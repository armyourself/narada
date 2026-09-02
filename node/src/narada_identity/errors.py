"""Errors raised by the narada identity layer."""


class NaradaIdentityError(Exception):
    """Base class for identity-layer errors."""


class NaradaKeystoreError(NaradaIdentityError):
    """Raised by the keystore when keys cannot be stored or loaded."""


class NaradaMnemonicError(NaradaIdentityError):
    """Raised when a BIP-39 mnemonic is invalid or cannot be generated."""


__all__ = [
    "NaradaIdentityError",
    "NaradaKeystoreError",
    "NaradaMnemonicError",
]
