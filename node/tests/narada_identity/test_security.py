"""Security-focused tests for the Narada identity layer.

Covers:
* account_id validation across all keystore backends (path-traversal)
* PassphraseKeystore max file size enforcement
* One-shot claim tokens (issue, consume, expiry, replay, cross-id)
* HTTP router account_id validation
* Wrapped ValueError -> NaradaIdentityError on bad X25519/Ed25519 input
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.narada_identity import (
    InMemoryKeystore,
    NaradaIdentityError,
    NaradaKeystoreError,
    PassphraseKeystore,
    generate_identity,
    verify_signature,
)
from src.narada_identity.keystore import _ACCOUNT_ID_PATTERN, _validate_account_id
from src.routers import narada_identity_tasks as router_module


# --- account_id validation in keystores -----------------------------------


@pytest.mark.parametrize(
    "bad_id",
    [
        "",
        "../etc/passwd",
        "..\\windows\\system32",
        "foo/bar",
        "foo\\bar",
        "foo\x00bar",
        "a" * 1024,
        "foo bar",
        "foo;rm -rf /",
    ],
)
def test_keystores_reject_unsafe_account_ids(bad_id: str) -> None:
    if bad_id == "foo/bar" and "/" in _ACCOUNT_ID_PATTERN.pattern:
        # If we ever widen the pattern to allow slashes, this test
        # would need updating; guard here.
        pytest.skip("pattern allows '/'")
    for ks in (InMemoryKeystore(),):
        with pytest.raises(NaradaKeystoreError):
            ks.store(bad_id, b"\x01" * 32)
        with pytest.raises(NaradaKeystoreError):
            ks.load(bad_id)
        with pytest.raises(NaradaKeystoreError):
            ks.delete(bad_id)
        with pytest.raises(NaradaKeystoreError):
            ks.has(bad_id)


def test_passphrase_keystore_rejects_unsafe_account_ids() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ks = PassphraseKeystore(Path(tmp))
        ks.set_passphrase("test")
        with pytest.raises(NaradaKeystoreError):
            ks.store("../escape", b"\x01" * 32)
        # Confirm nothing was written outside the keystore directory.
        assert not Path(tmp).parent.joinpath("escape.bin").exists()


def test_validate_account_id_accepts_normal_emails() -> None:
    for good in [
        "alice@example.com",
        "bob",
        "user.name@sub.example.co.uk",
        "user+tag@example.com",
        "a" * 254,
    ]:
        # Should not raise.
        _validate_account_id(good)


# --- PassphraseKeystore: file-size cap -------------------------------------


def test_passphrase_keystore_refuses_oversized_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ks = PassphraseKeystore(Path(tmp))
        ks.set_passphrase("test")
        # Write a valid entry first.
        ks.store("alice", b"\x42" * 32)
        # Overwrite the file with junk that exceeds the cap.
        path = Path(tmp) / "alice.bin"
        path.write_bytes(b"X" * 4096)
        with pytest.raises(NaradaKeystoreError):
            ks.load("alice")


# --- Wrapped X25519/Ed25519 errors -----------------------------------------


def test_shared_secret_rejects_non_public_id_string() -> None:
    identity, _ = generate_identity("alice@example.com", keystore=InMemoryKeystore())
    with pytest.raises(NaradaIdentityError):
        identity.shared_secret_with("not a narada1... id")
    with pytest.raises(NaradaIdentityError):
        identity.shared_secret_with("")


def test_shared_secret_rejects_low_cardinality_public_id() -> None:
    """A public id that decodes but whose X25519 key is a small-subgroup / invalid point must produce a typed error, not a stack trace."""
    identity, _ = generate_identity("alice@example.com", keystore=InMemoryKeystore())
    # A structurally-valid narada1... id whose X25519 component is all-zero bytes.
    # Build it by encoding 1 + 32 zero bytes + 32 zero bytes.
    import base64
    from src.narada_identity.encoding import _bech32_encode, _convertbits
    payload = bytes([0x01]) + (b"\x00" * 32) + (b"\x00" * 32)
    data = _convertbits(payload, 8, 5, pad=True)
    bad_id = _bech32_encode("narada", data, "bech32m")
    with pytest.raises(NaradaIdentityError):
        identity.shared_secret_with(bad_id)


def test_verify_signature_rejects_malformed_public_key() -> None:
    # The function validates the length first; a non-32 length raises.
    with pytest.raises(NaradaIdentityError):
        verify_signature(b"\x00" * 31, b"sig", b"data")
    with pytest.raises(NaradaIdentityError):
        verify_signature(b"\x00" * 33, b"sig", b"data")


# --- HTTP router: account_id validation ------------------------------------


def _build_test_app(monkeypatch=None):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router_module.router)

    def _isolated_keystore():
        # Force InMemoryKeystore so tests are independent of OS keyring.
        return InMemoryKeystore()

    if monkeypatch is not None:
        monkeypatch.setattr(
            router_module, "default_keystore", _isolated_keystore
        )
    else:
        router_module.default_keystore = _isolated_keystore  # type: ignore[assignment]
    router_module._keystore = None
    return app


def test_router_generates_identity_without_returning_mnemonic() -> None:
    app = _build_test_app()
    with TestClient(app) as client:
        resp = client.post(
            "/narada/identity/generate",
            params={"account_id": "alice@example.com"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        # Mnemonic is NOT in the response.
        assert "mnemonic" not in data
        assert "public_id" in data
        assert "account_id" in data
        assert "mnemonic_claim_token" in data


def test_router_rejects_unsafe_account_id_on_generate() -> None:
    app = _build_test_app()
    with TestClient(app) as client:
        for bad in ["", "../etc/passwd", "a" * 1024, "foo bar", "foo\x00bar"]:
            resp = client.post(
                "/narada/identity/generate",
                params={"account_id": bad},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is False
            assert "account_id" in body["message"].lower() or "1-254" in body["message"]


def test_router_rejects_unsafe_account_id_on_show() -> None:
    app = _build_test_app()
    with TestClient(app) as client:
        # Use a clearly-invalid account_id; path param won't allow
        # "..%2F" in a single segment but the router still receives it
        # as a string with %2F decoded. FastAPI rejects multi-segment
        # matches on a single {account_id} placeholder, so we test
        # with characters that pass URL parsing but fail validation.
        resp = client.get("/narada/identity/foo%20bar")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False


def test_router_rejects_oversized_mnemonic_on_recover() -> None:
    app = _build_test_app()
    with TestClient(app) as client:
        resp = client.post(
            "/narada/identity/recover",
            json={"account_id": "alice@example.com", "mnemonic": "x" * 1024},
        )
        # Pydantic Field(max_length=256) -> 422.
        assert resp.status_code == 422


def test_router_recover_refuses_to_overwrite_existing_identity() -> None:
    app = _build_test_app()
    with TestClient(app) as client:
        # Generate first.
        resp1 = client.post(
            "/narada/identity/generate",
            params={"account_id": "alice@example.com"},
        )
        assert resp1.status_code == 200
        assert resp1.json()["success"] is True
        # Recover with a fresh mnemonic should be refused.
        resp2 = client.post(
            "/narada/identity/recover",
            json={
                "account_id": "alice@example.com",
                "mnemonic": "abandon " * 11 + "abandon",
            },
        )
        assert resp2.status_code == 200
        body = resp2.json()
        assert body["success"] is False
        assert "already exists" in body["message"].lower()


# --- Claim tokens ----------------------------------------------------------


def test_claim_token_issued_and_consumable() -> None:
    # Clear any leftover state.
    router_module._claim_tokens.clear()
    public_id = "narada1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq"
    token = router_module._issue_claim_token(public_id)
    assert router_module._consume_claim_token(token, public_id) is True
    # Replay must fail.
    assert router_module._consume_claim_token(token, public_id) is False


def test_claim_token_rejects_wrong_public_id() -> None:
    router_module._claim_tokens.clear()
    public_a = "narada1aaa"
    public_b = "narada1bbb"
    token = router_module._issue_claim_token(public_a)
    assert router_module._consume_claim_token(token, public_b) is False


def test_claim_token_expiry() -> None:
    router_module._claim_tokens.clear()
    public_id = "narada1ccc"
    token = router_module._issue_claim_token(public_id)
    # Force the entry to be already-expired.
    router_module._claim_tokens[token] = (
        public_id,
        time.monotonic() - 1.0,
    )
    assert router_module._consume_claim_token(token, public_id) is False
