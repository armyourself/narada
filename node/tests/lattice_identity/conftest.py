"""Shared pytest fixtures and helpers for the Lattice identity tests."""

from __future__ import annotations

import pytest

from src.lattice_identity.keystore import InMemoryKeystore


@pytest.fixture
def in_memory_keystore() -> InMemoryKeystore:
    return InMemoryKeystore()
