# Changelog

All notable changes to Lattice will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and this project does not yet follow Semantic Versioning.

## [Unreleased]

### Changed

- **Restructured repository to the target Lattice layout:**
  - `app/` → `client/` (desktop client, SvelteKit + Tauri; runnable as before).
  - `server/` → `node/` (Lattice node daemon; Python / FastAPI; still speaks
    conventional IMAP/SMTP until the Lattice protocol layer lands).
  - `assets/` → `client/assets/`.
  - `docs/` split into `docs/architecture/`, `docs/protocol/`, and
    `docs/security/`.
  - `docs/INSTALLATION.md` → `docs/architecture/INSTALLATION.md`.
  - `docs/ROADMAP.md` → `docs/architecture/ROADMAP.md`.
  - `docs/screenshots/` → `docs/architecture/screenshots/`.
  - `install.sh` is preserved at the repo root for now; Windows-friendly
    equivalents live under `scripts/` (`install.ps1`, `dev.ps1`).
- **CI workflows updated** (`.github/workflows/build-and-release.yml`,
  `build-only.yml`, `virustotal-scan.yml`) to build from `client/` and
  `node/` and to produce `Lattice_*` artifacts.
- **Bumpversion configuration** (`.bumpversion.toml`) updated to point at
  `client/`, `node/`, and `gateway/` paths; added a `gateway/pyproject.toml`
  version target.
- **Root README rewritten** to describe the new layout and link into
  `protocol/`. The stray ` ```` ` fences from the previous version were
  removed.
- **Makefile** replaced with a small Windows- and POSIX-friendly set of
  targets: `install`, `install-win`, `run-node`, `run-client`, `test-node`.

### Added

- `gateway/` package skeleton: future home of the Lattice ↔ SMTP/IMAP
  bridge. Initially a `NotImplementedError` entry point plus a `pyproject.toml`
  and `README.md`.
- `protocol/` directory with stub documents:
  - `protocol/README.md` — overview of the protocol directory.
  - `protocol/spec.md` — top-level protocol goals, non-goals, layers, and
    open questions.
  - `protocol/identity.md` — cryptographic identity working draft.
  - `protocol/message-format.md` — encrypted message envelope working draft.
- `docs/security/README.md` — placeholder for the future threat model and
  audit notes.
- `scripts/install.ps1` — Windows installer for the node + client.
- `scripts/dev.ps1` — Windows dev launcher that spawns the node and client
  in separate terminal windows.

### Attribution

Lattice is forked from
[Openmail](https://github.com/burakorkmez/openmail) and remains
licensed under the Apache License 2.0. See [`LICENSE`](LICENSE).
