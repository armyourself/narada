import os
import tempfile
from pathlib import Path

import pytest

from src.lattice_identity.errors import LatticeKeystoreError
from src.lattice_identity.keystore import (
    InMemoryKeystore,
    KeyringKeystore,
    PassphraseKeystore,
)


def test_in_memory_store_load_delete():
    ks = InMemoryKeystore()
    seed = b"\x42" * 32
    ks.store("alice", seed)
    assert ks.has("alice")
    assert ks.load("alice") == seed
    assert ks.delete("alice") is True
    assert not ks.has("alice")


def test_in_memory_load_missing_raises():
    ks = InMemoryKeystore()
    with pytest.raises(LatticeKeystoreError):
        ks.load("ghost")


def test_in_memory_store_wrong_seed_length():
    ks = InMemoryKeystore()
    with pytest.raises(LatticeKeystoreError):
        ks.store("alice", b"too short")


def test_passphrase_keystore_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        ks = PassphraseKeystore(Path(tmp))
        ks.set_passphrase("correct horse battery staple")
        seed = os.urandom(32)
        ks.store("alice", seed)
        loaded = ks.load("alice")
        assert loaded == seed
        assert ks.delete("alice") is True
        assert not ks.has("alice")


def test_passphrase_keystore_wrong_passphrase_fails():
    with tempfile.TemporaryDirectory() as tmp:
        ks = PassphraseKeystore(Path(tmp))
        ks.set_passphrase("right")
        ks.store("alice", b"\x01" * 32)
        ks.set_passphrase("wrong")
        with pytest.raises(LatticeKeystoreError):
            ks.load("alice")


def test_passphrase_keystore_requires_passphrase():
    with tempfile.TemporaryDirectory() as tmp:
        ks = PassphraseKeystore(Path(tmp))
        with pytest.raises(LatticeKeystoreError):
            ks.store("alice", b"\x01" * 32)


def test_keyring_keystore_roundtrip_if_backend_available():
    """Smoke test for the OS keyring backend.

    Skipped if the keyring backend is the in-memory ``Fail`` (which is
    what keyring uses when no real backend is reachable, e.g. on Linux
    without ``SecretService``). The :class:`InMemoryKeystore` covers
    correctness in that case.
    """
    import keyring
    backend = keyring.get_keyring()
    if backend.__class__.__name__ == "Fail":
        pytest.skip("No real keyring backend available on this host.")
    ks = KeyringKeystore(service_prefix="lattice.tests.tmp")
    seed = os.urandom(32)
    try:
        ks.store("alice@example.com", seed)
        try:
            assert ks.load("alice@example.com") == seed
        finally:
            ks.delete("alice@example.com")
    except LatticeKeystoreError as exc:
        pytest.skip(f"Keyring backend not usable here: {exc}")
