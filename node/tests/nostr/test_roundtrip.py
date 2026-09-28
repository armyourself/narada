"""End-to-end Nostr round trip against an in-process fake relay.

Exercises the receive path production depends on, none of which the
unit tests cover:

1. ``NostrAdapter.connect()`` opens sockets that live on a persistent
   background loop (a per-call loop leaves them bound to a closed loop).
2. A background listener task is the socket's sole reader, so publish()
   can actually observe its OK acknowledgement.
3. Events published by Alice are dispatched to Bob's subscription
   callback, decrypted and persisted to Bob's mailbox JSONL.
4. Relays replay stored events on every REQ: replayed events must be
   deduplicated instead of appended again.
5. ``fetch_messages()`` serves the persisted events back as mail.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path

import pytest

from src.mail_abstraction.base import Address
from src.nostr.adapter import NostrAdapter
from src.nostr.config import NostrConfig
from src.nostr.identity import generate_nostr_identity


class FakeRelay:
    """Minimal NIP-01 relay: ACKs events, fans them out, replays on REQ."""

    def __init__(self) -> None:
        self.port: int | None = None
        self.published: list[dict] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server = None
        self._connections: list[dict] = []

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}"

    def start(self) -> str:
        loop = asyncio.new_event_loop()
        self._loop = loop
        ready = threading.Event()

        def _run() -> None:
            asyncio.set_event_loop(loop)

            async def main() -> None:
                import websockets

                async def handler(ws) -> None:
                    conn = {"ws": ws, "subs": set()}
                    self._connections.append(conn)
                    try:
                        async for message in ws:
                            await self._handle(conn, message)
                    finally:
                        if conn in self._connections:
                            self._connections.remove(conn)

                self._server = await websockets.serve(handler, "127.0.0.1", 0)
                self.port = self._server.sockets[0].getsockname()[1]
                ready.set()

            loop.run_until_complete(main())
            loop.run_forever()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        if not ready.wait(timeout=10):
            raise RuntimeError("Fake relay failed to start")
        return self.url

    async def _handle(self, conn: dict, message: str | bytes) -> None:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        if not isinstance(data, list) or not data:
            return

        kind = data[0]
        if kind == "EVENT" and len(data) >= 2:
            event = data[1]
            self.published.append(event)
            await conn["ws"].send(
                json.dumps(["OK", event.get("id", ""), True, ""])
            )
            for other in list(self._connections):
                if other is conn:
                    continue
                for sub_id in list(other["subs"]):
                    await other["ws"].send(
                        json.dumps(["EVENT", sub_id, event])
                    )
        elif kind == "REQ" and len(data) >= 2:
            conn["subs"].add(data[1])
            # Replay stored events, then EOSE -- like a real relay.
            for event in list(self.published):
                await conn["ws"].send(
                    json.dumps(["EVENT", data[1], event])
                )
            await conn["ws"].send(json.dumps(["EOSE", data[1]]))
        elif kind == "CLOSE" and len(data) >= 2:
            conn["subs"].discard(data[1])

    def stop(self) -> None:
        if self._loop is None:
            return

        async def _close() -> None:
            if self._server is not None:
                self._server.close()
                await self._server.wait_closed()

        try:
            asyncio.run_coroutine_threadsafe(_close(), self._loop).result(5)
        except Exception:
            pass
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except RuntimeError:
            pass
        if self._thread is not None:
            self._thread.join(timeout=5)


@pytest.fixture
def fake_relay():
    relay = FakeRelay()
    relay.start()
    yield relay
    relay.stop()


def _make_adapter(account_id: str, url: str, data_dir: Path) -> NostrAdapter:
    config = NostrConfig(relay_urls=[url], timeout_seconds=5.0)
    return NostrAdapter(
        account_id,
        identity=generate_nostr_identity(),
        config=config,
        data_dir=data_dir,
    )


def _wait_for(predicate, timeout: float = 10.0, interval: float = 0.1) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_send_receive_roundtrip(fake_relay, tmp_path):
    url = fake_relay.url
    alice = _make_adapter("alice@example.com", url, tmp_path / "alice")
    bob = _make_adapter("bob@example.com", url, tmp_path / "bob")

    try:
        ok, msg = alice.connect()
        assert ok, msg
        ok, msg = bob.connect()
        assert ok, msg
        # Phase 1c: connecting is enough to start receiving -- no extra
        # call is required to open the inbox subscription.
        assert bob._subscription_id is not None

        ok, msg = alice.send_message(
            from_address=Address(address=alice.identity.public_key_hex),
            to_addresses=[Address(address=bob.identity.public_key_hex)],
            subject="Round trip",
            body="It works",
        )
        assert ok, msg
        assert len(fake_relay.published) == 1

        arrived = _wait_for(lambda: bob.fetch_messages("nostr"))
        assert arrived, "event published by Alice never reached Bob"

        messages = bob.fetch_messages("nostr")
        assert len(messages) == 1
        assert messages[0].subject == "Round trip"
        assert messages[0].from_address.address == alice.identity.public_key_hex

        mailbox_path = tmp_path / "bob" / "etc" / "mailbox.bob@example.com.jsonl"
        assert mailbox_path.exists()
        lines = [ln for ln in mailbox_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["nostr_event_id"] == fake_relay.published[0]["id"]

        # Restart receive path: the relay replays its stored event on the
        # new REQ, and the dedup guard must keep the mailbox at one line.
        ok, msg = bob.disconnect()
        assert ok, msg
        ok, msg = bob.connect()
        assert ok, msg

        time.sleep(1.0)
        lines = [ln for ln in mailbox_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1, "replayed event was appended twice"
    finally:
        alice.disconnect()
        bob.disconnect()
