"""Nostr transport API endpoints.

These routes let the client register a Nostr identity, send/receive
messages via Nostr relays, and inspect relay status.  They sit beside
the existing IMAP/SMTP routes in ``mailbox_tasks`` and ``account_tasks``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src._types import Response
from src.helpers.uvicorn_logger import UvicornLogger
from src.internal.nostr_handler import NostrHandler
from src.mail_abstraction.base import Address, MessageSource

uvicorn_logger = UvicornLogger()
nostr_handler = NostrHandler()

router = APIRouter(tags=["Nostr"])


# ── request / response models ─────────────────────────────────────────────


class RegisterIdentityRequest(BaseModel):
    account: str
    npub: str
    nsec_hex: str


class GenerateIdentityRequest(BaseModel):
    account: str


class SendNostrEmailRequest(BaseModel):
    sender_npub: str
    recipient_npub: str
    subject: str
    body: str
    cc: list[str] = []


class NostrMailboxEntry(BaseModel):
    uid: str
    sender: str
    subject: str
    preview: str | None = None
    date: str
    source: str = "nostr"


# ── routes ────────────────────────────────────────────────────────────────


@router.post("/nostr/register-identity")
async def register_identity(request: RegisterIdentityRequest) -> Response:
    """Register a Nostr identity for an account.

    Called after the client generates or recovers a Nostr keypair.
    The server persists the identity and creates a NostrAdapter.
    """
    try:
        adapter = nostr_handler.store_identity(
            account_id=request.account,
            npub=request.npub,
            nsec_hex=request.nsec_hex,
        )
        ok, msg = adapter.connect()
        return Response(
            success=ok,
            message=msg,
            data={"npub": request.npub, "connected": ok},
        )
    except Exception as exc:
        from src.utils import err_msg
        return Response(success=False, message=err_msg("Identity registration failed.", str(exc)))


@router.post("/nostr/generate-identity")
async def generate_identity(request: GenerateIdentityRequest) -> Response:
    """Generate a new Nostr identity on the server and register it.

    Returns the npub (public key) and nsec_hex (secret key in hex)
    so the client can store them locally.
    """
    from src.nostr.identity import generate_nostr_identity
    try:
        identity = generate_nostr_identity()
        adapter = nostr_handler.store_identity(
            account_id=request.account,
            npub=identity.public_key_bech32,
            nsec_hex=identity.secret_key_hex,
        )
        ok, msg = adapter.connect()
        return Response(
            success=ok,
            message=msg or "Identity generated and registered",
            data={
                "npub": identity.public_key_bech32,
                "nsec_hex": identity.secret_key_hex,
                "pubkey_hex": identity.public_key_hex,
                "connected": ok,
            },
        )
    except Exception as exc:
        from src.utils import err_msg
        return Response(success=False, message=err_msg("Identity generation failed.", str(exc)))


@router.get("/nostr/get-identity/{account}")
async def get_identity(account: str) -> Response:
    """Return the Nostr public key (npub) for *account*."""
    adapter = nostr_handler.get_adapter(account)
    if adapter is None or adapter.identity is None:
        return Response(success=False, message=f"No Nostr identity for {account}")
    return Response(
        success=True,
        message="Identity fetched",
        data={"npub": adapter.identity.public_key_bech32},
    )


@router.get("/nostr/status/{account}")
async def nostr_status(account: str) -> Response:
    """Connection status for a Nostr account."""
    adapter = nostr_handler.get_adapter(account)
    if adapter is None:
        return Response(
            success=False,
            message=f"No Nostr adapter for {account}",
        )
    relay_count = adapter.relay_pool.connected_count()
    total_relays = len(adapter.relay_pool.relays)
    return Response(
        success=True,
        message="Nostr status",
        data={
            "connected": adapter.is_connected(),
            "relays_connected": relay_count,
            "relays_total": total_relays,
        },
    )


@router.get("/nostr/relays")
async def get_relays() -> Response:
    """Aggregate relay status across all adapters."""
    statuses = nostr_handler.get_relay_status()
    return Response(
        success=True,
        message="Relay status",
        data=statuses,
    )


@router.post("/nostr/send-email")
async def send_nostr_email(request: SendNostrEmailRequest) -> Response:
    """Send an email message via Nostr relays.

    The recipient address must be a Nostr public key (hex or npub).
    """
    adapter = nostr_handler.get_adapter(request.sender_npub)
    if adapter is None:
        # Try to find adapter by matching any registered npub
        for acc_id, a in nostr_handler.get_all_adapters().items():
            if a.identity and a.identity.public_key_bech32 == request.sender_npub:
                adapter = a
                break
    if adapter is None:
        return Response(
            success=False,
            message="No Nostr adapter found for the sender",
        )

    from src.nostr.identity import npub_decode
    try:
        recipient_hex = _resolve_npub(request.recipient_npub)
    except ValueError:
        return Response(success=False, message=f"Invalid recipient: {request.recipient_npub}")

    from src.mail_abstraction.base import Address
    from_addr = Address(address=adapter.identity.public_key_hex)
    to_addr = Address(address=recipient_hex)

    cc_addrs = []
    for cc_npub in request.cc:
        try:
            cc_hex = _resolve_npub(cc_npub)
            cc_addrs.append(Address(address=cc_hex))
        except ValueError:
            continue

    ok, msg = adapter.send_message(
        from_address=from_addr,
        to_addresses=[to_addr],
        subject=request.subject,
        body=request.body,
        cc=cc_addrs or None,
    )
    return Response(success=ok, message=msg)


@router.get("/nostr/get-mailbox/{account}")
async def get_nostr_mailbox(
    account: str,
    limit: int = 50,
    offset: int = 0,
) -> Response:
    """Fetch received Nostr messages from the local JSONL mailbox."""
    adapter = nostr_handler.get_adapter(account)
    if adapter is None:
        return Response(
            success=False,
            message=f"No Nostr adapter for {account}",
        )

    messages = adapter.fetch_messages("nostr", limit=limit, offset=offset)
    entries = [
        NostrMailboxEntry(
            uid=m.uid,
            sender=str(m.from_address),
            subject=m.subject,
            preview=m.preview,
            date=m.date or "",
            source=m.source if isinstance(m.source, str) else m.source.value,
        ).model_dump()
        for m in messages
    ]
    return Response(
        success=True,
        message="Nostr mailbox fetched",
        data=entries,
    )


# ── WebSocket subscription ───────────────────────────────────────────────


@router.websocket("/nostr/subscribe/{account}")
async def nostr_subscribe(websocket: WebSocket, account: str):
    """WebSocket endpoint for live Nostr message delivery.

    The server subscribes to incoming Nostr events and forwards them
    to the client as JSON messages.
    """
    await websocket.accept()
    uvicorn_logger.websocket(websocket, f"Nostr subscription opened for {account}")

    adapter = nostr_handler.get_adapter(account)
    if adapter is None:
        await websocket.close(reason=f"No Nostr adapter for {account}")
        return

    loop = asyncio.get_event_loop()
    send_queue: asyncio.Queue = asyncio.Queue()

    def _on_message(msg):
        asyncio.run_coroutine_threadsafe(
            send_queue.put({
                "uid": msg.uid,
                "sender": str(msg.from_address),
                "subject": msg.subject,
                "preview": msg.preview,
                "date": msg.date,
            }),
            loop,
        )

    sub_id = adapter.subscribe_for_messages(on_message=_on_message)

    try:
        while True:
            try:
                event = await asyncio.wait_for(send_queue.get(), timeout=30.0)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        uvicorn_logger.websocket(websocket, f"Nostr subscription error: {exc}")
    finally:
        try:
            adapter.relay_pool.unsubscribe_all(sub_id)
        except Exception:
            pass


# ── helpers ───────────────────────────────────────────────────────────────


def _resolve_npub(npub_or_hex: str) -> str:
    """Accept an npub or raw hex pubkey and return the hex form."""
    value = npub_or_hex.strip()
    if value.startswith("npub1"):
        from src.nostr.identity import npub_decode
        raw = npub_decode(value)
        return raw.hex()
    # Assume hex
    bytes.fromhex(value)  # validate
    if len(value) != 64:
        raise ValueError(f"Hex pubkey must be 64 chars, got {len(value)}")
    return value


__all__ = ["router"]
