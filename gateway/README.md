# Narada Gateway

The gateway bridges the [Narada protocol](../protocol/spec.md) with conventional
email infrastructure (SMTP/IMAP). It is the piece that lets Narada users talk
to Gmail, Outlook, and any other standard email address — and vice versa.

## Status

Phase 5 ships. The gateway is a library today; a long-running daemon that
polls IMAP and exposes a control API lands alongside the Phase 6 audit. The
deliverable is the **trust boundary**: identity mapping, Narada↔RFC822
conversion, and adapters that wrap the existing Openmail SMTP/IMAP clients.

Phase 5 covers:

- **Narada → SMTP** (forward outbound Narada messages as conventional email).
- **SMTP → Narada** (accept inbound SMTP and deliver into the Narada network).
- **Identity mapping** between conventional addresses and Narada public keys
  (no open relay, no anonymous inbound).

Deferred (held for Phase 6 alongside the audit, per project plan):

- **Narada → IMAP** (expose a Narada mailbox over IMAP for legacy clients).
- **IMAP → Narada** (bulk ingest of a legacy IMAP mailbox).
- Spam / rate limiting / reputation / DKIM / DANE / SRS / onion anonymity.
- Long-running daemon + control API.

## Layout

```
gateway/
├── gateway/            # Python package
│   ├── __init__.py
│   ├── __main__.py
│   ├── convert.py      # NaradaBody <-> RFC822 (EmailMessage)
│   ├── mapping.py      # IdentityMapping (JSON-backed)
│   ├── orchestrator.py # Gateway orchestrator (out + in)
│   ├── sender.py       # SmtpSender (wraps Openmail SMTPManager)
│   ├── receiver.py     # ImapReceiver (wraps Openmail IMAPManager)
│   └── errors.py
├── scripts/
│   └── smoke_phase5.py # Round-trips a message without a live SMTP/IMAP
├── tests/
├── pyproject.toml
└── README.md
```

## Run

Validate a mapping without sending anything:

```sh
cd gateway
uv run python -m gateway --mapping /etc/narada/gateway-mapping.json --check
```

The package is importable as `gateway.gateway` from the repo root or after
installation.

## Test

```sh
cd ..
python -m pytest gateway/tests/ -q
```

The smoke script exercises the full outbound path against an in-memory SMTP
transport:

```sh
cd ..
python gateway/scripts/smoke_phase5.py
```

## Identity mapping file

JSON, two top-level keys:

```json
{
  "narada_to_smtp": {
    "narada1qalice...": "alice@example.com"
  },
  "smtp_to_narada": {
    "alice@example.com": "narada1qalice..."
  }
}
```

`narada_to_smtp` is consulted on outbound; `smtp_to_narada` on inbound.
A conventional address must map to **exactly one** Narada id (Phase 5
invariant). Missing mappings are refused; the gateway cannot be used as an
open relay and refuses anonymous inbound.
