# Changelog

All notable changes to Lattice will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and this project does not yet follow Semantic Versioning.

## [Unreleased]

### Added

- **Mail Abstraction layer** under `node/src/mail_abstraction/`. Defines a
  single `MailAdapter` interface (`Address`, `Folder`, `Message`,
  `MessageSource`) that the Lattice node uses to talk to mail sources
  regardless of transport. Two adapters:
  - `IMAPSMTPAdapter` — wraps the existing `Openmail` IMAP/SMTP client.
    Transport methods (`list_folders`, `fetch_messages`, `send_message`,
    `watch`) currently raise `MailAdapterError` and will be migrated to
    use the interface as the routers are refactored; a `build_draft`
    helper is already wired for callers that want to keep the adapter
    contract in their signature.
  - `LatticeAdapter` — stub for the future Lattice protocol transport
    (Phase 2+ of the Lattice roadmap). All transport methods raise
    `MailAdapterError` with a clear "not yet implemented" message.
- **Lattice cryptographic identity** under `node/src/lattice_identity/`.
  Each Lattice account can now hold an identity consisting of an
  Ed25519 signing key and an X25519 encryption key, encoded as a
  `lattice1...` bech32m string (see `protocol/identity.md` for the
  spec). Includes:
  - `Keypair` with deterministic X25519 derivation (HKDF) from the
    Ed25519 seed.
  - BIP-39 12-word mnemonic generation and recovery.
  - Three keystore backends: `InMemoryKeystore` (tests), `KeyringKeystore`
    (OS keyring, production default), `PassphraseKeystore`
    (PBKDF2-HMAC-SHA256 + AES-GCM file fallback for headless servers).
  - HTTP router `lattice_identity_tasks` exposed under
    `/lattice/identity/generate`, `/lattice/identity/{account_id}`,
    `/lattice/identity/recover`, `/lattice/identity/rotate`,
    `/lattice/identity/{account_id}` (DELETE).
  - CLI: `python -m src.lattice_identity.cli generate|show|recover|rotate`.
- **`Account.lattice_identity_id`** optional field on the existing
  `Account` and `AccountWithPassword` models, defaulting to `None`.
- **42 new tests** under `node/tests/mail_abstraction/`,
  `node/tests/lattice_identity/`, and
  `node/tests/internal/test_account_lattice_field.py`. All pass.
- `mnemonic>=0.21` added to `node/pyproject.toml` dependencies.
- Concrete specification in `protocol/identity.md` (replaces the prior
  open-questions stub).

### Changed

- `node/src/main.py` now mounts the `lattice_identity_tasks` router
  alongside the existing account and mailbox routers. The HTTP API
  surface for existing endpoints is unchanged.
- `AccountManager`'s `Account` / `AccountWithPassword` models gained an
  optional `lattice_identity_id` field. No changes to existing fields
  or behaviour; existing tests continue to pass.
- `protocol/identity.md` rewritten from a stub into a concrete spec.

### Notes

- The router-cleanup work (migrating `account_tasks.py` and
  `mailbox_tasks.py` to call the new `MailAdapter` interface) is
  intentionally deferred. The abstraction is in place and tested; the
  migration will happen in a follow-up PR that exercises the adapter
  end-to-end. The reason: the existing routers call
  `IMAPManager.get_emails(folder, ...)`-style methods whose signatures
  do not match a clean `fetch_messages(folder)` adapter call (e.g.
  `get_emails` requires a prior `search_emails` call). A faithful
  refactor is its own PR.
- The pre-existing `test_account_manager.py` is sensitive to test
  ordering because its `setUpClass` does not clear the global
  `SecureStorage` between runs. This is unchanged by this commit; the
  pre-existing test suite was never designed to be re-run in the same
  process.

## [0.0.1-alpha0] - initial Openmail release and Lattice restructure

- Forked from https://github.com/burakorkmez/openmail. Desktop client
  (SvelteKit + Tauri), self-hosted server (Python / FastAPI), IMAP/SMTP
  support, multiple accounts, unified inbox, advanced search, bulk
  operations, undo actions.
- Restructured repository to the target Lattice layout:
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

## Attribution

Lattice is forked from
[Openmail](https://github.com/burakorkmez/openmail) and remains
licensed under the Apache License 2.0. See [`LICENSE`](LICENSE).
