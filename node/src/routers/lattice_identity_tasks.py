"""FastAPI routes for the Lattice identity layer.

The router intentionally does **not** persist anything on its own - it
delegates to the same ``AccountManager`` and keystore backends that the
rest of the Lattice node uses. The HTTP surface here is the API the
Lattice client (or operator scripts) call to manage identities.

A Lattice identity is keyed by ``account_id``, which is the conventional
email address of the account it's attached to. The keystore stores the
private seed; the public id is returned in responses.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from src._types import Response
from src.lattice_identity.errors import LatticeIdentityError
from src.lattice_identity.identity import (
    generate_identity,
    identity_from_keystore,
    identity_from_mnemonic,
    rotate_identity,
)
from src.lattice_identity.keystore import InMemoryKeystore, default_keystore
from src.utils import err_msg

router = APIRouter(tags=["Lattice Identity"])

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


class GenerateIdentityData(BaseModel):
    account_id: str
    public_id: str
    mnemonic: str


@router.post("/lattice/identity/generate")
def generate(account_id: str) -> Response[GenerateIdentityData]:
    try:
        identity, mnemonic = generate_identity(account_id, keystore=_get_keystore())
    except LatticeIdentityError as exc:
        return Response(success=False, message=err_msg("Failed to generate identity.", str(exc)))
    return Response[GenerateIdentityData](
        success=True,
        message="Identity generated. Store the mnemonic; it is the only backup.",
        data=GenerateIdentityData(
            account_id=identity.account_id,
            public_id=identity.public_id,
            mnemonic=mnemonic,
        ),
    )


class ShowIdentityData(BaseModel):
    account_id: str
    public_id: str


@router.get("/lattice/identity/{account_id}")
def show(account_id: str) -> Response[ShowIdentityData]:
    try:
        identity = identity_from_keystore(account_id, _get_keystore())
    except LatticeIdentityError as exc:
        return Response(success=False, message=err_msg("Failed to load identity.", str(exc)))
    return Response[ShowIdentityData](
        success=True,
        message="Identity loaded.",
        data=ShowIdentityData(
            account_id=identity.account_id,
            public_id=identity.public_id,
        ),
    )


class RecoverIdentityRequest(BaseModel):
    account_id: str
    mnemonic: str


@router.post("/lattice/identity/recover")
def recover(request: RecoverIdentityRequest) -> Response[ShowIdentityData]:
    try:
        identity = identity_from_mnemonic(
            request.account_id, request.mnemonic, keystore=_get_keystore()
        )
    except LatticeIdentityError as exc:
        return Response(success=False, message=err_msg("Failed to recover identity.", str(exc)))
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


@router.post("/lattice/identity/rotate")
def rotate(request: RotateIdentityRequest) -> Response[GenerateIdentityData]:
    try:
        identity, mnemonic = rotate_identity(request.account_id, _get_keystore())
    except LatticeIdentityError as exc:
        return Response(success=False, message=err_msg("Failed to rotate identity.", str(exc)))
    return Response[GenerateIdentityData](
        success=True,
        message="Identity rotated. Store the new mnemonic; the old one is now invalid.",
        data=GenerateIdentityData(
            account_id=identity.account_id,
            public_id=identity.public_id,
            mnemonic=mnemonic,
        ),
    )


@router.delete("/lattice/identity/{account_id}")
def delete(account_id: str) -> Response:
    try:
        removed = _get_keystore().delete(account_id)
    except LatticeIdentityError as exc:
        return Response(success=False, message=err_msg("Failed to delete identity.", str(exc)))
    if not removed:
        return Response(success=False, message="No identity to delete.")
    return Response(success=True, message="Identity deleted.")


__all__ = ["router"]
