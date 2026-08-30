"""Lattice Gateway entry point.

Planned responsibilities (Phase 5 of the Lattice roadmap):
    * Lattice -> SMTP: forward outbound Lattice messages as conventional email.
    * SMTP -> Lattice: accept inbound SMTP and deliver into the Lattice network.
    * Lattice -> IMAP: expose a Lattice mailbox over IMAP for legacy clients.
    * IMAP -> Lattice: ingest a legacy IMAP mailbox into the Lattice network.
    * Identity mapping between conventional addresses and Lattice public keys.
    * Spam and abuse handling at the trust boundary.

For now this is a skeleton. The IMAP/SMTP client code lives with the Lattice
node in ``node/src/modules/openmail/{imap,smtp}.py`` and will be moved or
re-exported from here as the gateway implementation matures.
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError(
        "Lattice gateway is not implemented yet. "
        "See gateway/gateway/__init__.py and docs/protocol for the plan."
    )


if __name__ == "__main__":
    main()
