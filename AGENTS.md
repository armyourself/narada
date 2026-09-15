# AGENTS.md

## Project Overview

Narada is an alpha-grade decentralized email infrastructure. It's a monorepo with three packages:

- `node/` - Python/FastAPI node daemon (core protocol)
- `client/` - SvelteKit + Tauri desktop client
- `gateway/` - Python bridge between Narada and conventional SMTP/IMAP

**Important**: This is research-grade software. Not production-ready.

## Development Setup

### Prerequisites

- Python 3.13+ and [uv](https://github.com/astral-sh/uv)
- [Bun](https://bun.sh) and [Rust toolchain](https://tauri.app/start/prerequisites/)

### Install

Linux/macOS: `./install.sh`
Windows: `pwsh -File scripts/install.ps1`

### Run

- **Node daemon**: `cd node && uv run python -m src.main`
- **Desktop client**: `cd client && bun run tauri dev`
- **Windows dev**: `pwsh -File scripts/dev.ps1` (spawns both)

## Testing

- **Node tests**: `cd node && uv run pytest`
- **Gateway tests**: `cd gateway && uv run pytest` (inferred from structure)
- **Client typecheck**: `cd client && bun run check`
- No global test runner; each package runs independently.

## Architecture Notes

### Monorepo Structure

- `node/` contains the core Narada protocol, identity, P2P, relay, and routing
- `client/` is a SvelteKit app wrapped with Tauri for desktop
- `gateway/` depends on `Narada-node` (see `gateway/pyproject.toml`)
- `protocol/` contains design docs (identity, message format)
- `tools/` and `scripts/` contain shared dev helpers

### Key Technical Facts

- Node daemon uses FastAPI with uvicorn
- Identity: Ed25519 + X25519 keys, bech32m public IDs, BIP-39 mnemonics
- Transport: QUIC with framed JSON envelopes
- Storage: JSONL files in data directories
- Protocol is not yet formalized (Phase 6 pending)

### Version Management

Version bumps via `bumpversion` (`.bumpversion.toml`). Updates files:
- `node/pyproject.toml`
- `gateway/pyproject.toml`
- `client/package.json`
- `client/src-tauri/tauri.conf.json`
- `client/src-tauri/Cargo.toml`
- Documentation files

## Conventions

- Python code follows PEP 8; no linter config found
- Client uses Svelte 5 with TypeScript
- Commit messages follow conventional commits (from bumpversion config)
- All code is Apache 2.0 licensed (fork of Openmail)

## Gotchas

- Gateway depends on `Narada-node` package; ensure it's installed first
- Node data directories are created at runtime (`<data_dir>/`)
- QUIC transport uses self-signed TLS certs with TOFU pinning
- No hot-reload for the node daemon; restart required for changes
- Client dev server requires both Bun and Rust toolchain
