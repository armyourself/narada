# Narada Gateway

The gateway bridges the [Narada protocol](../protocol/spec.md) with conventional
email infrastructure (SMTP/IMAP). It is the piece that lets Narada users talk
to Gmail, Outlook, and any other standard email address — and vice versa.

## Status

Phase 5 is **complete**. The gateway ships:

- **Narada → SMTP** (forward outbound Narada messages as conventional email).
- **SMTP → Narada** (accept inbound SMTP and deliver into the Narada network).
- **Narada → IMAP** (read-only IMAP server exposing the Narada mailbox to
  legacy email clients).
- **IMAP → Narada** (bulk ingest of a legacy IMAP mailbox into the Narada store).
- **Identity mapping** between conventional addresses and Narada public keys
  (no open relay, no anonymous inbound).
- **Long-running daemon** with IMAP polling, optional IMAP server, and a
  REST control API (`/status`, `/poll`, `/reload`).

Deferred (held for Phase 6 alongside the audit):

- Spam / rate limiting / reputation / DKIM / DANE / SRS / onion anonymity.

## Layout

```
gateway/
├── gateway/              # Python package
│   ├── __init__.py
│   ├── __main__.py       # CLI entry point (check, daemon, ingest, serve-imap, ...)
│   ├── convert.py        # NaradaBody <-> RFC822 (EmailMessage)
│   ├── mapping.py        # IdentityMapping (JSON-backed)
│   ├── orchestrator.py   # Gateway orchestrator (outbound + inbound)
│   ├── sender.py         # SmtpSender (wraps Openmail SMTPManager)
│   ├── receiver.py       # ImapReceiver (wraps Openmail IMAPManager)
│   ├── imap_server.py    # NaradaImapServer (read-only IMAP4rev1 server)
│   ├── ingester.py       # ImapIngester (bulk IMAP → Narada import)
│   ├── daemon.py         # GatewayDaemon (long-running polling daemon)
│   ├── daemon_control.py # ControlServer (REST API for the daemon)
│   └── errors.py
├── scripts/
│   └── smoke_phase5.py   # Round-trips a message without a live SMTP/IMAP
├── tests/
├── pyproject.toml
└── README.md
```

## CLI Commands

```sh
# Validate a mapping
python -m gateway check --mapping mapping.json

# Start the long-running daemon
python -m gateway daemon --mapping mapping.json \
    --smtp-host smtp.example.com --imap-host imap.example.com \
    --imap-server-port 1143 --control-port 1144

# Bulk-import from IMAP into Narada
python -m gateway ingest --mapping mapping.json \
    --imap-host imap.example.com --imap-user alice@example.com --limit 100

# Start a read-only IMAP server for the Narada mailbox
python -m gateway serve-imap --data-dir ~/.openmail --port 1143

# Query a running daemon
python -m gateway status --control-port 1144
python -m gateway poll --control-port 1144
python -m gateway reload --control-port 1144
```

## Control API

When the daemon is running, query it via HTTP on `127.0.0.1:<control-port>`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | `{"ok": true}` |
| `/status` | GET | Daemon status (poll count, last result, mapping sizes) |
| `/poll` | POST | Trigger one inbound poll cycle |
| `/reload` | POST | Reload the identity mapping from disk |

## Test

```sh
cd gateway
python -m pytest tests/ -q
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
