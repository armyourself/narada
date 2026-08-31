"""Shared pytest fixtures for Lattice protocol tests."""

from __future__ import annotations

import pytest

from src.lattice_identity.identity import generate_identity
from src.lattice_identity.keystore import InMemoryKeystore


@pytest.fixture
def in_memory_keystore() -> InMemoryKeystore:
    return InMemoryKeystore()


@pytest.fixture
def alice_identity(in_memory_keystore):
    identity, _ = generate_identity("alice@example.com", keystore=in_memory_keystore)
    return identity


@pytest.fixture
def bob_identity(in_memory_keystore):
    identity, _ = generate_identity("bob@example.com", keystore=in_memory_keystore)
    return identity
