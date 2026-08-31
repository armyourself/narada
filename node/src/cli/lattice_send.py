"""CLI: send a Lattice message from the command line.

Usage:

    python -m src.cli.lattice_send <account_id> <recipient_public_id> \\
        --subject "hi" --body "hello"

The Lattice identity for ``account_id`` is loaded from the keystore
the same way the rest of the node does it. The message is sealed,
then either delivered directly (if the recipient is in the local
contact list) or queued in the outbox for retry.
"""

from __future__ import annotations

import argparse
import sys
import time

from src.lattice.adapter import LatticeAdapter
from src.lattice_identity.keystore import default_keystore
from src.mail_abstraction import Address


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lattice-send",
        description="Send a Lattice message from the command line.",
    )
    p.add_argument("account_id", help="local account whose Lattice identity to use")
    p.add_argument("recipient_public_id", help="recipient's lattice1... public id")
    p.add_argument("--subject", default="", help="message subject")
    p.add_argument("--body", default="", help="message body text")
    p.add_argument("--from-name", default="", help="display name for the sender")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    adapter = LatticeAdapter(args.account_id, keystore=default_keystore())
    from_address = Address(address=args.account_id, name=args.from_name or None)
    to_address = Address(address=args.recipient_public_id, name=None)
    try:
        ok, msg = adapter.send_message(
            from_address=from_address,
            to_addresses=[to_address],
            subject=args.subject,
            body=args.body,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(("ok" if ok else "queued") + ": " + msg)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
