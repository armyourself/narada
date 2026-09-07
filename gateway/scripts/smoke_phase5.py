#!/usr/bin/env python3
"""Smoke script for Phase 5.

Round-trips a Narada body through the gateway without a live
SMTP/IMAP connection. Useful as a manual integration check that
the conversion + mapping + sender wiring is correct after a
fresh checkout.

Usage::

    cd ..
    python gateway/scripts/smoke_phase5.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
# Make the gateway + node packages importable when running from
# a checkout.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "node"))

from gateway.gateway.convert import (  # noqa: E402
    narada_body_to_rfc822,
    rfc822_to_narada_body,
)
from gateway.gateway.mapping import IdentityMapping  # noqa: E402
from gateway.gateway.orchestrator import Gateway  # noqa: E402
from gateway.gateway.sender import SmtpSender  # noqa: E402
from src.narada_identity.identity import generate_identity  # noqa: E402
from src.narada_identity.keystore import InMemoryKeystore  # noqa: E402


def main() -> int:
    keystore = InMemoryKeystore()
    alice_identity, _ = generate_identity("alice@example.com", keystore=keystore)
    bob_identity, _ = generate_identity("bob@example.com", keystore=keystore)
    alice_id = alice_identity.public_id
    bob_id = bob_identity.public_id

    mapping = IdentityMapping(
        narada_to_smtp={
            alice_id: "alice@example.com",
            bob_id: "bob@example.com",
        },
        smtp_to_narada={
            "alice@example.com": alice_id,
            "bob@example.com": bob_id,
        },
    )
    sent: list = []

    def _transport(msg) -> tuple[bool, str]:
        sent.append(msg)
        return True, "250 OK"

    sender = SmtpSender(transport=_transport, smtp_from="gateway@example.com")
    gw = Gateway(mapping=mapping, sender=sender)

    body = {
        "subject": "Phase 5 smoke",
        "sender": f"Alice <{alice_id}>",
        "to": [bob_id],
        "cc": [],
        "body_text": "hello bob, this is the gateway smoke test",
        "sent_at": 1735689600,
    }
    ok, response = gw.deliver_outbound(
        narada_recipient_id=bob_id,
        body=body,
    )
    print(json.dumps({"outbound_ok": ok, "response": response}, indent=2))
    if not ok:
        return 1
    if not sent:
        print("no message was sent", file=sys.stderr)
        return 1
    msg = sent[-1]
    print(
        json.dumps(
            {
                "to": msg.get("To"),
                "from": msg.get("From"),
                "subject": msg.get("Subject"),
                "body": msg.get_content(),
            },
            indent=2,
        )
    )
    recovered = rfc822_to_narada_body(msg)
    print(json.dumps(recovered, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
