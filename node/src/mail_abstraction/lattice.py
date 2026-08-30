"""Stub Lattice protocol adapter.

This is the seam where the Lattice protocol (Phases 2+ of the Lattice
roadmap) will plug in. Every transport method currently raises
``NotImplementedError`` with a clear message. The adapter exists today so
that:

* The :class:`MailAdapter` interface has a second concrete implementation,
  which makes the interface itself exerciseable in tests.
* Future PRs have an obvious home for the Lattice transport code without
  having to refactor the interface or re-route callers.
"""

from __future__ import annotations

from typing import Callable, Optional

from .base import (
    Address,
    Folder,
    MailAdapter,
    MailAdapterError,
    Message,
    MessageSource,
)


class LatticeAdapter(MailAdapter):
    """Stub adapter for the future Lattice protocol transport."""

    source = MessageSource.LATTICE

    def __init__(self, *, node_url: Optional[str] = None) -> None:
        self._node_url = node_url
        self._connected = False

    @property
    def node_url(self) -> Optional[str]:
        return self._node_url

    def connect(self) -> tuple[bool, str]:
        raise MailAdapterError(
            "LatticeAdapter.connect is not implemented; the Lattice "
            "protocol transport lands in Phase 2 of the Lattice roadmap."
        )

    def disconnect(self) -> tuple[bool, str]:
        if not self._connected:
            return True, "Not connected."
        self._connected = False
        return True, "Disconnected."

    def is_connected(self) -> bool:
        return self._connected

    def list_folders(self) -> list[Folder]:
        raise MailAdapterError(
            "LatticeAdapter.list_folders is not implemented; the Lattice "
            "protocol transport lands in Phase 2 of the Lattice roadmap."
        )

    def fetch_messages(
        self,
        folder: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Message]:
        raise MailAdapterError(
            "LatticeAdapter.fetch_messages is not implemented; the Lattice "
            "protocol transport lands in Phase 2 of the Lattice roadmap."
        )

    def send_message(
        self,
        *,
        from_address: Address,
        to_addresses: list[Address],
        subject: str,
        body: str,
        cc: Optional[list[Address]] = None,
        bcc: Optional[list[Address]] = None,
        attachments: Optional[list[tuple[str, bytes]]] = None,
        is_html: bool = False,
    ) -> tuple[bool, str]:
        raise MailAdapterError(
            "LatticeAdapter.send_message is not implemented; the Lattice "
            "protocol transport lands in Phase 2 of the Lattice roadmap."
        )

    def watch(self, folder: str, on_new_message: Callable[[Message], None]) -> None:
        raise MailAdapterError(
            "LatticeAdapter.watch is not implemented; the Lattice "
            "protocol transport lands in Phase 2 of the Lattice roadmap."
        )


__all__ = ["LatticeAdapter"]
