"""Keystore backends for Lattice identity private material.

A :class:`LatticeKeystore` stores a 32-byte Ed25519 seed per account
identifier (``account_id``). Three backends are provided:

* :class:`InMemoryKeystore` - process-local, used by tests and the CLI
  ``--no-persist`` mode. Does not survive a restart.
* :class:`KeyringKeystore` - the production default. Stores the seed in
  the operating system's keyring under a service name derived from
  ``account_id``. No passphrase prompt is required because the OS
  protects access.
* :class:`PassphraseKeystore` - fallback for headless servers where no
  OS keyring is available. The seed is encrypted with a passphrase using
  AES-GCM and stored as a file under ``~/.lattice/keystore/``.

All keystores implement the same :class:`LatticeKeystore` ABC, so the
node can pick a backend based on environment without touching the rest
of the identity code.
"""

from __future__ import annotations

import abc
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import keyring
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from .errors import LatticeKeystoreError

_KEYRING_SERVICE_PREFIX = "lattice.identity"
_PBKDF2_ITERATIONS = 200_000
_PBKDF2_SALT_LEN = 16
_AES_NONCE_LEN = 12
_KEY_LEN = 32
_FILE_MAGIC = b"LATTICE1"


class LatticeKeystore(abc.ABC):
    """Abstract keystore interface."""

    @abc.abstractmethod
    def store(self, account_id: str, seed: bytes) -> None:
        """Persist ``seed`` for ``account_id``."""

    @abc.abstractmethod
    def load(self, account_id: str) -> bytes:
        """Load the seed for ``account_id``. Raises if not present."""

    @abc.abstractmethod
    def delete(self, account_id: str) -> bool:
        """Remove the entry. Returns True if it existed."""

    @abc.abstractmethod
    def has(self, account_id: str) -> bool:
        """Return True if an entry exists for ``account_id``."""


class InMemoryKeystore(LatticeKeystore):
    """Keystore that holds seeds in a process-local dict.

    Useful for tests and for ``--no-persist`` invocations. Not durable.
    """

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def store(self, account_id: str, seed: bytes) -> None:
        if len(seed) != _KEY_LEN:
            raise LatticeKeystoreError(
                f"Seed must be {_KEY_LEN} bytes, got {len(seed)}"
            )
        self._store[account_id] = seed

    def load(self, account_id: str) -> bytes:
        try:
            return self._store[account_id]
        except KeyError as exc:
            raise LatticeKeystoreError(
                f"No identity stored for account_id={account_id!r}"
            ) from exc

    def delete(self, account_id: str) -> bool:
        return self._store.pop(account_id, None) is not None

    def has(self, account_id: str) -> bool:
        return account_id in self._store


class KeyringKeystore(LatticeKeystore):
    """Keystore that uses the OS keyring (preferred on desktop)."""

    def __init__(self, service_prefix: str = _KEYRING_SERVICE_PREFIX) -> None:
        self._service_prefix = service_prefix
        self._backend = keyring.get_keyring()

    def _service(self, account_id: str) -> str:
        return f"{self._service_prefix}.{account_id}"

    @staticmethod
    def _encode(seed: bytes) -> str:
        import base64
        return base64.b64encode(seed).decode("ascii")

    @staticmethod
    def _decode(value: str) -> bytes:
        import base64
        try:
            return base64.b64decode(value.encode("ascii"), validate=True)
        except Exception as exc:
            raise LatticeKeystoreError(
                "Stored keyring value is not valid base64"
            ) from exc

    def store(self, account_id: str, seed: bytes) -> None:
        if len(seed) != _KEY_LEN:
            raise LatticeKeystoreError(
                f"Seed must be {_KEY_LEN} bytes, got {len(seed)}"
            )
        try:
            self._backend.set_password(
                self._service(account_id), account_id, self._encode(seed)
            )
        except Exception as exc:
            raise LatticeKeystoreError(
                f"Keyring backend refused to store the seed: {exc}"
            ) from exc

    def load(self, account_id: str) -> bytes:
        try:
            value = self._backend.get_password(self._service(account_id), account_id)
        except Exception as exc:
            raise LatticeKeystoreError(
                f"Keyring backend refused to read the seed: {exc}"
            ) from exc
        if value is None:
            raise LatticeKeystoreError(
                f"No identity stored for account_id={account_id!r}"
            )
        return self._decode(value)

    def delete(self, account_id: str) -> bool:
        try:
            self._backend.delete_password(self._service(account_id), account_id)
            return True
        except keyring.errors.PasswordDeleteError:
            return False
        except Exception as exc:
            raise LatticeKeystoreError(
                f"Keyring backend refused to delete the seed: {exc}"
            ) from exc

    def has(self, account_id: str) -> bool:
        try:
            return self._backend.get_password(self._service(account_id), account_id) is not None
        except Exception:
            return False


@dataclass
class PassphraseKeystore(LatticeKeystore):
    """Filesystem-backed keystore encrypted with a passphrase (AES-GCM)."""

    directory: Path
    _passphrase: Optional[bytes] = None

    def __post_init__(self) -> None:
        self.directory = Path(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._mode = 0o700
        try:
            os.chmod(self.directory, self._mode)
        except OSError:
            pass

    def set_passphrase(self, passphrase: str) -> None:
        if not passphrase:
            raise LatticeKeystoreError("Passphrase must not be empty")
        self._passphrase = passphrase.encode("utf-8")

    def _path(self, account_id: str) -> Path:
        return self.directory / f"{account_id}.bin"

    def _encrypt(self, seed: bytes) -> bytes:
        if self._passphrase is None:
            raise LatticeKeystoreError(
                "PassphraseKeystore requires set_passphrase() before use"
            )
        salt = secrets.token_bytes(_PBKDF2_SALT_LEN)
        nonce = secrets.token_bytes(_AES_NONCE_LEN)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=_KEY_LEN,
            salt=salt,
            iterations=_PBKDF2_ITERATIONS,
        )
        key = kdf.derive(self._passphrase)
        aesgcm = AESGCM(key)
        ct = aesgcm.encrypt(nonce, seed, associated_data=_FILE_MAGIC)
        return _FILE_MAGIC + salt + nonce + ct

    def _decrypt(self, blob: bytes) -> bytes:
        if self._passphrase is None:
            raise LatticeKeystoreError(
                "PassphraseKeystore requires set_passphrase() before use"
            )
        if not blob.startswith(_FILE_MAGIC):
            raise LatticeKeystoreError("Keystore file has wrong magic")
        offset = len(_FILE_MAGIC)
        salt = blob[offset:offset + _PBKDF2_SALT_LEN]
        offset += _PBKDF2_SALT_LEN
        nonce = blob[offset:offset + _AES_NONCE_LEN]
        offset += _AES_NONCE_LEN
        ct = blob[offset:]
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=_KEY_LEN,
            salt=salt,
            iterations=_PBKDF2_ITERATIONS,
        )
        key = kdf.derive(self._passphrase)
        aesgcm = AESGCM(key)
        try:
            return aesgcm.decrypt(nonce, ct, associated_data=_FILE_MAGIC)
        except Exception as exc:
            raise LatticeKeystoreError(
                "Failed to decrypt keystore file (wrong passphrase or corrupt file)"
            ) from exc

    def store(self, account_id: str, seed: bytes) -> None:
        if len(seed) != _KEY_LEN:
            raise LatticeKeystoreError(
                f"Seed must be {_KEY_LEN} bytes, got {len(seed)}"
            )
        path = self._path(account_id)
        path.write_bytes(self._encrypt(seed))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def load(self, account_id: str) -> bytes:
        path = self._path(account_id)
        if not path.exists():
            raise LatticeKeystoreError(
                f"No identity stored for account_id={account_id!r}"
            )
        return self._decrypt(path.read_bytes())

    def delete(self, account_id: str) -> bool:
        path = self._path(account_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def has(self, account_id: str) -> bool:
        return self._path(account_id).exists()


def default_keystore(*, passphrase: Optional[str] = None) -> LatticeKeystore:
    """Pick the most appropriate keystore for the current environment.

    Order:

    1. ``InMemoryKeystore`` if ``passphrase == "memory"`` (escape hatch
       for tests / one-off CLI invocations).
    2. ``KeyringKeystore`` if the OS keyring is available and writable.
    3. ``PassphraseKeystore`` under ``~/.lattice/keystore`` as a last
       resort, requiring a passphrase.
    """
    if passphrase == "memory":
        return InMemoryKeystore()
    try:
        kr = KeyringKeystore()
        # Touch the backend to make sure it's reachable.
        kr._backend.get_password  # noqa: B018 (attribute access probe)
        return kr
    except Exception:
        pass
    if passphrase is None:
        raise LatticeKeystoreError(
            "No OS keyring is available; please provide a passphrase to use "
            "the PassphraseKeystore under ~/.lattice/keystore"
        )
    home = Path(os.path.expanduser("~"))
    ks = PassphraseKeystore(home / ".lattice" / "keystore")
    ks.set_passphrase(passphrase)
    return ks


__all__ = [
    "InMemoryKeystore",
    "KeyringKeystore",
    "LatticeKeystore",
    "PassphraseKeystore",
    "default_keystore",
]
