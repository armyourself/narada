# AGENTS.md

## Project Overview

Narada is an alpha-grade decentralized email application using Nostr transport. It's a monorepo with two packages:

- `node/` - Python/FastAPI server (core application)
- `client/` - SvelteKit + Tauri desktop client

**Important**: This is research-grade software. Not production-ready.

## Development Setup

### Prerequisites

- Python 3.13+ and [uv](https://github.com/astral-sh/uv)
- [Bun](https://bun.sh) and [Rust toolchain](https://tauri.app/start/prerequisites/)

### Install

Linux/macOS: `./install.sh`
Windows: `pwsh -File scripts/install.ps1`

### Run

- **Server**: `cd node && uv run python -m src.main`
- **Desktop client**: `cd client && bun run tauri dev`
- **Windows dev**: `pwsh -File scripts/dev.ps1` (spawns both)

## Testing

- **Node tests**: `cd node && uv run pytest`
- **Client typecheck**: `cd client && bun run check`
- No global test runner; each package runs independently.

## Architecture Notes

### Monorepo Structure

- `node/` contains the server: mail abstraction, Nostr transport, IMAP/SMTP, identity, API routers
- `client/` is a SvelteKit app wrapped with Tauri for desktop
- `docs/` and `scripts/` contain documentation and dev helpers

### Key Technical Facts

- Server uses FastAPI with uvicorn
- Identity: Ed25519 + X25519 keys, NIP-19 bech32 encoding (npub/nsec)
- Transport: Nostr relays via WebSocket (NIP-01, NIP-04, NIP-19)
- Storage: JSONL files in data directories
- Email: IMAP/SMTP via Openmail module

### Version Management

Version bumps via `bumpversion` (`.bumpversion.toml`). Updates files:
- `node/pyproject.toml`
- `client/package.json`
- `client/src-tauri/tauri.conf.json`
- `client/src-tauri/Cargo.toml`
- Documentation files

## Conventions

- Python code follows PEP 8; no linter config found
- Client uses Svelte 5 with TypeScript
- Commit messages follow conventional commits (from bumpversion config)
- All code is Apache 2.0 licensed (derived from Openmail)

## Gotchas

- Node data directories are created at runtime (`<data_dir>/`)
- No hot-reload for the server; restart required for changes
- Client dev server requires both Bun and Rust toolchain
- Nostr relay connectivity depends on network access to configured relays
