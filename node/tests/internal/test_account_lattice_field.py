"""Tests for the Lattice identity-related extensions to Account/AccountWithPassword.

These tests intentionally do not touch the live ``SecureStorage`` singleton
(the existing ``test_account_manager.py`` does). They only verify that the
``lattice_identity_id`` field round-trips through the Pydantic models.
"""

from __future__ import annotations

from src.internal.account_manager import Account, AccountWithPassword


def test_account_default_has_no_lattice_identity():
    a = Account(email_address="alice@example.com")
    assert a.lattice_identity_id is None


def test_account_can_carry_lattice_identity():
    a = Account(
        email_address="alice@example.com",
        lattice_identity_id="lattice1abc",
    )
    assert a.lattice_identity_id == "lattice1abc"


def test_account_with_password_carries_lattice_identity():
    a = AccountWithPassword(
        email_address="alice@example.com",
        encrypted_password="deadbeef",
        lattice_identity_id="lattice1xyz",
    )
    assert a.lattice_identity_id == "lattice1xyz"
    assert a.encrypted_password == "deadbeef"


def test_account_serialises_with_lattice_identity():
    a = Account(
        email_address="alice@example.com",
        fullname="Alice",
        lattice_identity_id="lattice1qrs",
    )
    payload = a.model_dump()
    assert payload["email_address"] == "alice@example.com"
    assert payload["lattice_identity_id"] == "lattice1qrs"
    # Round-trip back.
    a2 = Account.model_validate(payload)
    assert a2.lattice_identity_id == "lattice1qrs"
