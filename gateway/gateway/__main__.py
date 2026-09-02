"""Narada Gateway entry point.

Planned responsibilities (Phase 5 of the Narada roadmap):
    * Narada -> SMTP: forward outbound Narada messages as conventional email.
    * SMTP -> Narada: accept inbound SMTP and deliver into the Narada network.
    * Narada -> IMAP: expose a Narada mailbox over IMAP for legacy clients.
    * IMAP -> Narada: ingest a legacy IMAP mailbox into the Narada network.
    * Identity mapping between conventional addresses and Narada public keys.
    * Spam and abuse handling at the trust boundary.

For now this is a skeleton. The IMAP/SMTP client code lives with the Narada
node in ``node/src/modules/openmail/{imap,smtp}.py`` and will be moved or
re-exported from here as the gateway implementation matures.
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError(
        "Narada gateway is not implemented yet. "
        "See gateway/gateway/__init__.py and docs/protocol for the plan."
    )


if __name__ == "__main__":
    main()
