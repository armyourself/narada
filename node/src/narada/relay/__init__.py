"""Narada relay package (Phase 4).

Pieces:

* :mod:`.store`  -- encrypted per-recipient relay store with TTL,
  per-recipient and global quotas, and a tombstone-log-backed
  index that survives a disk tamper event.
* :mod:`.selector` -- sender-side policy that picks a relay from a
  :class:`src.narada.p2p.listener.PeerBook`, honouring the V2
  mailbox-discovery hint first.
* :mod:`.receipt` -- build/sign the best-effort ``relay.stored``
  receipt that the relay returns to the sender.
* :mod:`.handlers` -- ``relay.deposit`` / ``relay.fetch`` /
  ``relay.drop`` frames for the existing QUIC
  :class:`HandlerRegistry`.

The store does not see plaintext; only the encrypted envelope. See
:doc:`/protocol/relay` for the wire format.
"""

from .receipt import (
    RECEIPT_VERSION,
    StoredReceipt,
    make_stored_receipt,
    verify_stored_receipt,
)
from .selector import RelaySelector, SelectedRelay
from .handlers import (
    build_deposit_handler,
    build_drop_handler,
    build_fetch_handler,
    register_relay_handlers,
)
from .store import (
    DEFAULT_MAX_TTL_SECONDS,
    DEFAULT_MAX_TOTAL_BYTES,
    DEFAULT_MAX_TOTAL_DEPOSITS,
    DEFAULT_MAX_BYTES_PER_RECIPIENT,
    DEFAULT_MAX_DEPOSITS_PER_RECIPIENT,
    DEFAULT_TTL_SECONDS,
    RelayStore,
    RelayStoreError,
    StoredDeposit,
)

__all__ = [
    "DEFAULT_MAX_BYTES_PER_RECIPIENT",
    "DEFAULT_MAX_DEPOSITS_PER_RECIPIENT",
    "DEFAULT_MAX_TOTAL_BYTES",
    "DEFAULT_MAX_TOTAL_DEPOSITS",
    "DEFAULT_MAX_TTL_SECONDS",
    "DEFAULT_TTL_SECONDS",
    "RECEIPT_VERSION",
    "RelaySelector",
    "RelayStore",
    "RelayStoreError",
    "SelectedRelay",
    "StoredDeposit",
    "StoredReceipt",
    "build_deposit_handler",
    "build_drop_handler",
    "build_fetch_handler",
    "make_stored_receipt",
    "register_relay_handlers",
    "verify_stored_receipt",
]
