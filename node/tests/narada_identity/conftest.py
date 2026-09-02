"""Shared pytest fixtures and helpers for the narada identity tests."""

from __future__ import annotations

import pytest

from src.narada_identity.keystore import InMemoryKeystore


@pytest.fixture
def in_memory_keystore() -> InMemoryKeystore:
    return InMemoryKeystore()
