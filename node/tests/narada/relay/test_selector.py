"""Unit tests for :mod:`src.narada.relay.selector`."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from src.narada.relay.selector import RelaySelector


@dataclass
class _FakeState:
    endpoint: str
    last_seen: float = field(default_factory=time.time)
    down: bool = False
    missed_pings: int = 0
    node_id: str | None = None


@dataclass
class _FakePeerBook:
    states: list[_FakeState]

    def all(self) -> list[_FakeState]:
        return list(self.states)

    def get(self, endpoint: str):
        for s in self.states:
            if s.endpoint == endpoint:
                return s
        return None

    def live_endpoints(self) -> list[str]:
        return [s.endpoint for s in self.states if not s.down]


def test_fallback_to_peer_book():
    pb = _FakePeerBook(
        states=[
            _FakeState(endpoint="10.0.0.1:4440"),
            _FakeState(endpoint="10.0.0.2:4440"),
        ]
    )
    sel = RelaySelector()
    picked = sel.select(peer_book=pb, recipient_public_id="narada1qtest")
    assert picked is not None
    assert picked.reason == "fallback"
    assert picked.endpoint in {"10.0.0.1:4440", "10.0.0.2:4440"}


def test_down_peers_are_skipped():
    pb = _FakePeerBook(
        states=[
            _FakeState(endpoint="10.0.0.1:4440", down=True),
            _FakeState(endpoint="10.0.0.2:4440"),
        ]
    )
    sel = RelaySelector()
    picked = sel.select(peer_book=pb, recipient_public_id="narada1qtest")
    assert picked is not None
    assert picked.endpoint == "10.0.0.2:4440"


def test_cooldown_excludes_endpoint():
    pb = _FakePeerBook(states=[_FakeState(endpoint="10.0.0.1:4440")])
    sel = RelaySelector()
    sel.note_attempt("10.0.0.1:4440")
    picked = sel.select(peer_book=pb, recipient_public_id="narada1qtest")
    assert picked is None


def test_exclude_endpoints():
    pb = _FakePeerBook(
        states=[
            _FakeState(endpoint="10.0.0.1:4440"),
            _FakeState(endpoint="10.0.0.2:4440"),
        ]
    )
    sel = RelaySelector()
    picked = sel.select(
        peer_book=pb,
        recipient_public_id="narada1qtest",
        exclude_endpoints={"10.0.0.1:4440"},
    )
    assert picked is not None
    assert picked.endpoint == "10.0.0.2:4440"


def test_hint_overrides_fallback():
    pb = _FakePeerBook(
        states=[
            _FakeState(endpoint="10.0.0.1:4440", node_id="node1hi"),
            _FakeState(endpoint="10.0.0.2:4440"),
        ]
    )
    sel = RelaySelector()
    # V2 hint TLV: type 0x01, length 0x07, value "node1hi" (7 chars).
    recipient = "narada1" + ("a" * 30) + "\x01\x07node1hi"
    picked = sel.select(peer_book=pb, recipient_public_id=recipient)
    assert picked is not None
    assert picked.endpoint == "10.0.0.1:4440"
    assert picked.reason == "hint"
