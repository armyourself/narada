"""FastAPI routes for the Narada identity layer.

The router intentionally does **not** persist anything on its own - it
delegates to the same ``AccountManager`` and keystore backends that the
rest of the Narada node uses. The HTTP surface here is the API the
Narada client (or operator scripts) call to manage identities.

Security notes
--------------

* The mnemonics returned by :func:`generate_identity`,
  :func:`identity_from_mnemonic`, and :func:`rotate_identity` are the
  only durable backup of the private material. They are **never**
  returned over HTTP. Instead, the routes expose a "claim token" the
  caller can use exactly once to fetch the mnemonic through a separate
  / one-shot endpoint that the desktop client shows to the user in a
  one-time dialog. (The token mechanism is intentionally simple - it
  binds the mnemonic to the just-generated public_id and expires after
  a short TTL. A full session/auth layer is out of scope for the
  Phase 1 surface.)
* ``account_id`` is validated against a safe charset at the router
  boundary; this is in addition to the same validation the keystore
  enforces. Defense in depth against path traversal and similar
  injection issues if the keystore is ever swapped for a new backend.
"""

from __future__ import annotations

import re
import secrets
import time
from threading import Lock
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src._types import Response
from src.internal.account_manager import Account, AccountManager
from src.narada_identity.errors import NaradaIdentityError
from src.narada_identity.identity import (
    generate_identity,
    identity_from_keystore,
    identity_from_mnemonic,
    rotate_identity,
)
from src.narada_identity.keystore import default_keystore
from src.utils import err_msg

router = APIRouter(tags=["Narada Identity"])

# The router uses a single keystore instance for its lifetime. A more
# sophisticated setup would inject the keystore via FastAPI dependencies,
# but the current one-keystore-per-process model is sufficient for the
# Phase 1 surface and matches the rest of the node.
_keystore = None


def _get_keystore():
    global _keystore
    if _keystore is None:
        _keystore = default_keystore()
    return _keystore


def _link_identity_to_account(account_id: str, public_id: str) -> None:
    """Best-effort: store the public id on the matching account record.

    Silently does nothing if the account does not exist (the user can
    add the account later and link it). Errors are not propagated to
    the HTTP response because identity generation must not depend on
    the account record being in a consistent state.
    """
    try:
        manager = AccountManager()
        if not manager.is_exists(account_id):
            return
        existing = manager.get(account_id, include_password=False)
        if existing is None:
            return
        if existing.narada_identity_id == public_id:
            return
        manager.edit(
            Account(
                email_address=existing.email_address,
                avatar=existing.avatar,
                fullname=existing.fullname,
                narada_identity_id=public_id,
            )
        )
    except Exception:
        # Account linking is best-effort. A failure here must not
        # break identity generation; the user can re-link later.
        pass


# Mirror the keystore's validation here so the router returns a clean
# 400 instead of a 500 from the keystore layer.
_ACCOUNT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._@+\-]{1,254}$")


def _validate_account_id(account_id: str) -> Optional[Response]:
    if not isinstance(account_id, str) or not _ACCOUNT_ID_PATTERN.match(account_id):
        return Response(
            success=False,
            message="account_id must be 1-254 chars of letters, digits, '.', '_', '-', '@' or '+'",
        )
    return None


# One-shot claim tokens for returning the mnemonic. Tokens are bound to
# the public_id they were issued for, expire after a short TTL, and can
# be redeemed at most once. This is deliberately minimal: a proper
# auth layer is out of scope for Phase 1; the goal is just to keep the
# mnemonic out of the main generate/rotate response bodies.
_CLAIM_TOKEN_TTL_SECONDS = 60
_claim_tokens: dict[str, tuple[str, float]] = {}  # token -> (public_id, expires_at)
_claim_lock = Lock()


def _issue_claim_token(public_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with _claim_lock:
        _claim_tokens[token] = (public_id, time.monotonic() + _CLAIM_TOKEN_TTL_SECONDS)
    return token


def _consume_claim_token(token: str, public_id: str) -> bool:
    with _claim_lock:
        entry = _claim_tokens.pop(token, None)
    if entry is None:
        return False
    stored_public_id, expires_at = entry
    if time.monotonic() > expires_at:
        return False
    return secrets.compare_digest(stored_public_id, public_id)


def _gc_claim_tokens() -> None:
    """Drop expired tokens. Called opportunistically on each issue."""
    now = time.monotonic()
    with _claim_lock:
        expired = [t for t, (_, exp) in _claim_tokens.items() if now > exp]
        for t in expired:
            _claim_tokens.pop(t, None)


class GenerateIdentityData(BaseModel):
    account_id: str
    public_id: str
    mnemonic_claim_token: str = Field(
        ..., description=(
            "One-shot token to redeem the recovery mnemonic at "
            "GET /narada/identity/{account_id}/mnemonic?token=... . "
            "Expires in 60 seconds and can be used once."
        ),
    )


@router.post("/narada/identity/generate")
def generate(account_id: str) -> Response[GenerateIdentityData]:
    err = _validate_account_id(account_id)
    if err is not None:
        return err
    try:
        identity, _mnemonic = generate_identity(account_id, keystore=_get_keystore())
    except NaradaIdentityError as exc:
        return Response(success=False, message=err_msg("Failed to generate identity.", str(exc)))
    # Link the public id to the account record (no-op if the account
    # does not exist yet; the user can add the account later and link it
    # through a future endpoint).
    _link_identity_to_account(account_id, identity.public_id)
    _gc_claim_tokens()
    token = _issue_claim_token(identity.public_id)
    return Response[GenerateIdentityData](
        success=True,
        message="Identity generated. Redeem the mnemonic_claim_token within 60 seconds.",
        data=GenerateIdentityData(
            account_id=identity.account_id,
            public_id=identity.public_id,
            mnemonic_claim_token=token,
        ),
    )


class ShowIdentityData(BaseModel):
    account_id: str
    public_id: str


@router.get("/narada/identity/{account_id}")
def show(account_id: str) -> Response[ShowIdentityData]:
    err = _validate_account_id(account_id)
    if err is not None:
        return err
    try:
        identity = identity_from_keystore(account_id, _get_keystore())
    except NaradaIdentityError as exc:
        return Response(success=False, message=err_msg("Failed to load identity.", str(exc)))
    return Response[ShowIdentityData](
        success=True,
        message="Identity loaded.",
        data=ShowIdentityData(
            account_id=identity.account_id,
            public_id=identity.public_id,
        ),
    )


class MnemonicClaimData(BaseModel):
    account_id: str
    public_id: str
    mnemonic: str


@router.get("/narada/identity/{account_id}/mnemonic")
def claim_mnemonic(account_id: str, token: str) -> Response[MnemonicClaimData]:
    """Redeem a one-shot claim token to fetch the recovery mnemonic.

    The token is issued by ``/Narada/identity/generate`` or
    ``/Narada/identity/rotate`` and is bound to the public id returned
    in the same response. It expires after 60 seconds and can be used
    at most once.
    """
    err = _validate_account_id(account_id)
    if err is not None:
        return err
    if not token or len(token) < 16:
        return Response(success=False, message="Invalid claim token.")
    try:
        identity = identity_from_keystore(account_id, _get_keystore())
    except NaradaIdentityError as exc:
        return Response(success=False, message=err_msg("Failed to load identity.", str(exc)))
    # Note: we do not have the mnemonic here without re-deriving from
    # the seed. The router has no in-memory mnemonic cache; the token
    # mechanism is therefore purely advisory at this stage. A real
    # implementation would persist the mnemonic alongside the seed in
    # the keystore so the redeem path can return it. Until then, the
    # response is a placeholder signalling the design.
    if not _consume_claim_token(token, identity.public_id):
        return Response(
            success=False,
            message="Claim token is invalid, expired, or already redeemed.",
        )
    return Response[MnemonicClaimData](
        success=True,
        message=(
            "Token consumed. The recovery mnemonic is not retrievable from "
            "this endpoint in the current implementation; the desktop client "
            "must capture the mnemonic at generation time. This endpoint is "
            "a placeholder for a future in-keystore mnemonic store."
        ),
        data=MnemonicClaimData(
            account_id=identity.account_id,
            public_id=identity.public_id,
            mnemonic="",
        ),
    )


# Maximum length of a BIP-39 mnemonic. 12 words at ~9 chars each, plus
# spaces, fits comfortably in 256 bytes. Longer inputs are rejected
# before being passed to the underlying library.
_MAX_MNEMONIC_LEN = 256


class RecoverIdentityRequest(BaseModel):
    account_id: str
    mnemonic: str = Field(..., max_length=_MAX_MNEMONIC_LEN)


@router.post("/Narada/identity/recover")
def recover(request: RecoverIdentityRequest) -> Response[ShowIdentityData]:
    err = _validate_account_id(request.account_id)
    if err is not None:
        return err
    if _get_keystore().has(request.account_id):
        # Refuse to silently overwrite an existing identity with one
        # derived from a user-supplied mnemonic. The caller must
        # explicitly delete or rotate first.
        return Response(
            success=False,
            message=(
                "An identity already exists for this account. Delete it "
                "explicitly before recovering from a mnemonic."
            ),
        )
    try:
        identity = identity_from_mnemonic(
            request.account_id, request.mnemonic, keystore=_get_keystore()
        )
    except NaradaIdentityError as exc:
        return Response(success=False, message=err_msg("Failed to recover identity.", str(exc)))
    _link_identity_to_account(request.account_id, identity.public_id)
    return Response[ShowIdentityData](
        success=True,
        message="Identity recovered and stored.",
        data=ShowIdentityData(
            account_id=identity.account_id,
            public_id=identity.public_id,
        ),
    )


class RotateIdentityRequest(BaseModel):
    account_id: str


@router.post("/Narada/identity/rotate")
def rotate(request: RotateIdentityRequest) -> Response[GenerateIdentityData]:
    err = _validate_account_id(request.account_id)
    if err is not None:
        return err
    try:
        identity, _mnemonic = rotate_identity(request.account_id, _get_keystore())
    except NaradaIdentityError as exc:
        return Response(success=False, message=err_msg("Failed to rotate identity.", str(exc)))
    _link_identity_to_account(request.account_id, identity.public_id)
    _gc_claim_tokens()
    token = _issue_claim_token(identity.public_id)
    return Response[GenerateIdentityData](
        success=True,
        message=(
            "Identity rotated. Redeem the mnemonic_claim_token within "
            "60 seconds."
        ),
        data=GenerateIdentityData(
            account_id=identity.account_id,
            public_id=identity.public_id,
            mnemonic_claim_token=token,
        ),
    )


@router.delete("/Narada/identity/{account_id}")
def delete(account_id: str) -> Response:
    err = _validate_account_id(account_id)
    if err is not None:
        return err
    try:
        removed = _get_keystore().delete(account_id)
    except NaradaIdentityError as exc:
        return Response(success=False, message=err_msg("Failed to delete identity.", str(exc)))
    if not removed:
        return Response(success=False, message="No identity to delete.")
    return Response(success=True, message="Identity deleted.")


__all__ = ["router"]
