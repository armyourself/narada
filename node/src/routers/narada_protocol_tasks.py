"""FastAPI routes for the Narada protocol (Phase 2 MVP).

The router is the receiver side of the protocol. It accepts a sealed
Narada envelope over HTTP, validates it, decrypts it, and persists
it to the recipient's account mailbox.

Endpoints:

  * ``POST /Narada/inbox``  - receive an envelope.
  * ``GET  /Narada/inbox/{account_id}``  - list persisted envelopes
    (for debugging / client polling).
  * ``POST /Narada/outbox/retry``  - force-flush a given account's
    pending outbox (debugging / manual retry).

The router is intentionally narrow. The full outbox drain loop
lives in :class:`src.narada.adapter.NaradaAdapter.drain_outbox`,
called by the FastAPI lifespan task.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from src._types import Response
from src.narada_identity.keystore import default_keystore

from ..Narada.adapter import NaradaAdapter
from ..Narada.envelope import NaradaEnvelope, NaradaEnvelopeError
from ..Narada.inbox import NaradaInbox

router = APIRouter(tags=["Narada Protocol"])

# Mirror the keystore's validation here so the router returns a clean
# 400 instead of a 500 from the keystore layer.
_ACCOUNT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._@+\-]{1,254}$")

# Module-level knobs that the test suite overrides. Production code
# relies on the defaults: real OS keyring + ~/.openmail data dir.
_keystore_factory = default_keystore
_data_dir_factory = None  # None means "use default node data dir"


def _validate_account_id(account_id: str) -> Optional[Response]:
    if not isinstance(account_id, str) or not _ACCOUNT_ID_PATTERN.match(account_id):
        return Response(
            success=False,
            message="account_id must be 1-254 chars of letters, digits, '.', '_', '-', '@' or '+'",
        )
    return None


def _safe(account_id: str) -> str:
    return "".join(c if c.isalnum() or c in "._@+-" else "_" for c in account_id) or "unknown"


@router.post("/Narada/inbox")
def receive_envelope(envelope: Mapping[str, Any]) -> Response:
    """Receive a sealed Narada envelope from another node."""
    try:
        env = NaradaEnvelope.from_dict(envelope)
    except NaradaEnvelopeError as exc:
        return Response(success=False, message=f"invalid envelope: {exc}")

    account_id = _account_id_for_public_id(env.recipient_public_id)
    if account_id is None:
        return Response(
            success=False,
            message="no local account matches the envelope's recipient public id",
        )

    err = _validate_account_id(account_id)
    if err is not None:
        return err

    data_dir = _data_dir_factory() if _data_dir_factory is not None else None
    seen_path = data_dir / "etc" / f"seen.{_safe(account_id)}.json" if data_dir is not None else None
    inbox = NaradaInbox(
        account_id,
        keystore=_keystore_factory(),
        data_dir=data_dir,
        seen_path=seen_path,
    )
    try:
        body, was_duplicate = inbox.receive(env)
    except NaradaEnvelopeError as exc:
        return Response(success=False, message=f"envelope rejected: {exc}")

    return Response(
        success=True,
        message=("envelope accepted (duplicate, no re-persist)" if was_duplicate else "envelope accepted"),
        data={
            "message_id": env.message_id,
            "duplicate": was_duplicate,
            "subject": body.subject,
            "from": body.sender or env.sender_public_id,
        },
    )


@router.get("/narada/inbox/{account_id}")
def list_inbox(account_id: str) -> Response:
    err = _validate_account_id(account_id)
    if err is not None:
        return err
    try:
        adapter = NaradaAdapter(
            account_id,
            keystore=_keystore_factory(),
            data_dir=_data_dir_factory() if _data_dir_factory is not None else None,
        )
    except Exception as exc:  # noqa: BLE001
        return Response(success=False, message=f"could not open inbox: {exc}")
    messages = adapter.fetch_messages("narada", limit=200, offset=0)
    return Response(
        success=True,
        message=f"inbox for {account_id}",
        data={"messages": [m.__dict__ | {"source": m.source.value} for m in messages]},
    )


class OutboxRetryRequest(BaseModel):
    account_id: str


@router.post("/narada/outbox/retry")
def retry_outbox(request: OutboxRetryRequest) -> Response:
    err = _validate_account_id(request.account_id)
    if err is not None:
        return err
    try:
        adapter = NaradaAdapter(
            request.account_id,
            keystore=_keystore_factory(),
            data_dir=_data_dir_factory() if _data_dir_factory is not None else None,
        )
        attempts = adapter.drain_outbox(max_per_account=128)
    except Exception as exc:  # noqa: BLE001
        return Response(success=False, message=f"retry failed: {exc}")
    return Response(success=True, message="outbox drain attempted", data={"attempts": attempts})


def _account_id_for_public_id(public_id: str) -> Optional[str]:
    """Find the local account_id that owns ``public_id``.

    Today there is no separate identity-to-account registry; the
    adapter loads the Narada identity directly from the keystore
    using the account_id. The :class:`AccountManager` carries
    ``narada_identity_id`` on each account (set by the
    narada_identity router on generation), so we walk the
    ``AccountManager`` here.
    """
    from src.internal.account_manager import AccountManager

    try:
        manager = AccountManager()
    except Exception:
        return None
    try:
        accounts = manager.get_all(include_passwords=False)
    except Exception:
        return None
    for account in accounts:
        if account.narada_identity_id == public_id:
            return account.email_address
    return None


__all__ = ["router"]
