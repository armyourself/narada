# Narada Node

The Narada node is a long-running daemon that a user (or operator) runs to
participate in the Narada network. It is responsible for:

- Holding the user's **cryptographic identity** and **mailbox** (Phase 1+).
- **Encrypting** outbound messages to recipients and **decrypting** inbound ones.
- **Routing** messages across the Narada network via other independently
  operated nodes (Phase 3+).
- **Temporarily storing** messages in encrypted form for offline recipients
  when running as a relay (Phase 4+).
- Speaking conventional **IMAP/SMTP** to the local desktop client
  (`client/`) and bridging with `gateway/` for non-Narada peers (Phase 5+).

## Status

This directory currently contains the Openmail-derived FastAPI server. It
still speaks conventional email (IMAP/SMTP) only — the Narada protocol layer
will be added on top of this code. The directory is named `node/` to reflect
its target role.

## Layout

```
node/
├── src/
│   ├── main.py            # FastAPI app entry point
│   ├── internal/          # Account / client / storage managers
│   ├── modules/openmail/  # IMAP / SMTP / parsing / encoding (Openmail-derived)
│   ├── routers/           # FastAPI route definitions
│   └── helpers/           # Uvicorn logger, port scanner, etc.
├── tests/                 # Pytest test suite
├── assets/icons/          # App icon for the bundled server executable
├── pyproject.toml
└── README.md
```

## Run

Prerequisites:

- Python 3.13+
- [uv](https://github.com/astral-sh/uv)

```sh
cd node
uv sync
uv run python -m src.main
```

## Test

```sh
cd node
uv run pytest
```
