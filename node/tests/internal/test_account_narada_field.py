"""Tests for the Narada identity-related extensions to Account/AccountWithPassword.

These tests intentionally do not touch the live ``SecureStorage`` singleton
(the existing ``test_account_manager.py`` does). They only verify that the
``narada_identity_id`` field round-trips through the Pydantic models.
"""

from __future__ import annotations

from src.internal.account_manager import Account, AccountWithPassword


def test_account_default_has_no_narada_identity():
    a = Account(email_address="alice@example.com")
    assert a.narada_identity_id is None


def test_account_can_carry_narada_identity():
    a = Account(
        email_address="alice@example.com",
        narada_identity_id="narada1abc",
    )
    assert a.narada_identity_id == "narada1abc"


def test_account_with_password_carries_narada_identity():
    a = AccountWithPassword(
        email_address="alice@example.com",
        encrypted_password="deadbeef",
        narada_identity_id="narada1xyz",
    )
    assert a.narada_identity_id == "narada1xyz"
    assert a.encrypted_password == "deadbeef"


def test_account_serialises_with_narada_identity():
    a = Account(
        email_address="alice@example.com",
        fullname="Alice",
        narada_identity_id="narada1qrs",
    )
    payload = a.model_dump()
    assert payload["email_address"] == "alice@example.com"
    assert payload["narada_identity_id"] == "narada1qrs"
    # Round-trip back.
    a2 = Account.model_validate(payload)
    assert a2.narada_identity_id == "narada1qrs"
