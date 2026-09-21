"""Shared pytest fixtures for Nostr tests."""

from __future__ import annotations

import pytest

from src.nostr.identity import NostrIdentity, generate_nostr_identity


@pytest.fixture
def alice_nostr_identity() -> NostrIdentity:
    return generate_nostr_identity()


@pytest.fixture
def bob_nostr_identity() -> NostrIdentity:
    return generate_nostr_identity()
