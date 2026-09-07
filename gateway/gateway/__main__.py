"""Narada Gateway entry point (Phase 5).

The Phase 5 entry point is intentionally minimal: the gateway is
a library today, exercised by tests and integration scripts. A
long-running daemon that polls IMAP and serves a control API
will land alongside the Phase 6 audit; for now this entry point
loads the mapping, builds the orchestrator, and runs a single
dry cycle so an operator can verify the wiring.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .mapping import IdentityMapping
from .orchestrator import Gateway
from .sender import SmtpSender


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="narada-gateway",
        description="Narada <-> SMTP/IMAP gateway (Phase 5)",
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        required=True,
        help="Path to the identity-mapping JSON file.",
    )
    parser.add_argument(
        "--smtp-host",
        default="",
        help="SMTP host (omit to wire only the mapping).",
    )
    parser.add_argument(
        "--smtp-port",
        type=int,
        default=587,
        help="SMTP port (default 587).",
    )
    parser.add_argument(
        "--smtp-user",
        default="",
        help="SMTP username (omit for a no-credentials dry run).",
    )
    parser.add_argument(
        "--smtp-password",
        default="",
        help="SMTP password.",
    )
    parser.add_argument(
        "--smtp-from",
        default="",
        help="Default From: address when the body has none.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the mapping and exit without sending.",
    )
    args = parser.parse_args(argv)

    mapping = IdentityMapping.from_file(args.mapping)
    sender = SmtpSender(
        smtp_host=args.smtp_host,
        smtp_port=args.smtp_port,
        username=args.smtp_user,
        password=args.smtp_password,
        smtp_from=args.smtp_from,
    )
    gw = Gateway(mapping=mapping, sender=sender)
    summary = {
        "narada_ids": sorted(gw.mapping.narada_ids()),
        "smtp_addresses": sorted(gw.mapping.smtp_addresses()),
    }
    if args.check:
        json.dump(summary, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    sys.stdout.write(
        "Gateway wired. A long-running daemon will ship alongside "
        "the Phase 6 audit; for now run `python -m gateway --check "
        "--mapping <file>` to validate the mapping.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
