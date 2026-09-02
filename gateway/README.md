# Narada Gateway

The gateway bridges the [Narada protocol](../protocol/spec.md) with conventional
email infrastructure (SMTP/IMAP). It is the piece that lets Narada users talk
to Gmail, Outlook, and any other standard email address — and vice versa.

## Status

Skeleton. The IMAP/SMTP client logic currently lives with the Narada node
under `node/src/modules/openmail/{imap,smtp}.py`. Once the Narada protocol
delivery path is in place, the gateway will either consume those modules
directly or move a copy of them here.

## Planned responsibilities (Phase 5 of the Narada roadmap)

- **Narada -> SMTP**: forward outbound Narada messages as conventional email.
- **SMTP -> Narada**: accept inbound SMTP and deliver into the Narada network.
- **Narada -> IMAP**: expose a Narada mailbox over IMAP for legacy clients.
- **IMAP -> Narada**: ingest a legacy IMAP mailbox into the Narada network.
- **Identity mapping** between conventional addresses and Narada public keys.
- **Spam and abuse handling** at the trust boundary.

## Layout

```
gateway/
├── gateway/            # Python package
│   ├── __init__.py
│   └── __main__.py
├── pyproject.toml
└── README.md
```

## Run

Not implemented yet:

```sh
cd gateway
uv run python -m gateway
```
