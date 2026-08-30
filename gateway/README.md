# Lattice Gateway

The gateway bridges the [Lattice protocol](../protocol/spec.md) with conventional
email infrastructure (SMTP/IMAP). It is the piece that lets Lattice users talk
to Gmail, Outlook, and any other standard email address — and vice versa.

## Status

Skeleton. The IMAP/SMTP client logic currently lives with the Lattice node
under `node/src/modules/openmail/{imap,smtp}.py`. Once the Lattice protocol
delivery path is in place, the gateway will either consume those modules
directly or move a copy of them here.

## Planned responsibilities (Phase 5 of the Lattice roadmap)

- **Lattice -> SMTP**: forward outbound Lattice messages as conventional email.
- **SMTP -> Lattice**: accept inbound SMTP and deliver into the Lattice network.
- **Lattice -> IMAP**: expose a Lattice mailbox over IMAP for legacy clients.
- **IMAP -> Lattice**: ingest a legacy IMAP mailbox into the Lattice network.
- **Identity mapping** between conventional addresses and Lattice public keys.
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
