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

### Security

Aggressive security review of the Lattice identity layer landed in this
release. Highlights:

- **Path-traversal vulnerability fixed in `PassphraseKeystore`.** The
  `account_id` is now validated against a safe charset
  (`[A-Za-z0-9._@+-]{1,254}`) at the keystore boundary. Previously an
  HTTP caller could pass `account_id="../../etc/foo"` and have the
  keystore write outside the configured directory. Validation is
  enforced in every `LatticeKeystore` backend, not just the
  filesystem one, as defense in depth.
- **Mnemonic no longer echoed in HTTP response bodies.** The previous
  `/lattice/identity/generate` and `/lattice/identity/rotate` endpoints
  returned the 12-word recovery phrase in the JSON response, which is
  a total compromise of the keypair if the response is intercepted or
  logged. They now return a one-shot claim token instead. The mnemonic
  must be captured by the desktop client at generation time and is
  never sent over the network. A
  `GET /lattice/identity/{account_id}/mnemonic?token=...` redeem
  endpoint is in place; it currently returns a placeholder until the
  keystore grows an in-keystore mnemonic store, and the mechanism
  exists to keep the contract stable.
- **Recover endpoint refuses to silently overwrite an existing
  identity.** Previously, calling `/lattice/identity/recover` would
  silently replace the existing seed with the user-supplied mnemonic.
  The user could lose the old identity by mis-typing. Now the
  endpoint refuses to overwrite and tells the caller to delete or
  rotate first.
- **`cryptography` `ValueError` is now caught and re-raised as
  `LatticeIdentityError`.** Bad X25519 public keys (small-subgroup /
  invalid-curve points) and malformed Ed25519 public keys used to
  leak a 500 with a stack trace. They now produce a typed error that
  the HTTP router turns into a 4xx response.
- **Atomic keystore writes.** `PassphraseKeystore.store` now writes
  to `<account>.bin.tmp` and `os.replace`s into place, so a crash
  mid-write can no longer leave a half-written file the user would
  later fail to decrypt.
- **Max file size on keystore reads.** `PassphraseKeystore.load`
  now refuses to read files larger than 1 KiB. The on-disk format is
  ~84 bytes; a larger file indicates tampering or a stray drop into
  the keystore directory.
- **`account_id` is validated at the HTTP router boundary** with a
  `Response` 400-style failure, in addition to the keystore-layer
  check. The router also limits the mnemonic field to 256 chars via
  Pydantic to avoid passing huge strings to the BIP-39 library.
- **`assert` in `encoding.encode_public_id` replaced with an explicit
  `LatticeIdentityError` raise** so the length check survives
  `python -O`.
- **Unused imports removed** (`hmac` from `keypair.py`, the now-
  exported `generate_keypair` from `identity.py`).
- **`KeyringKeystore` probe in `default_keystore` now calls
  `get_password` with a no-op service** rather than accessing an
  attribute, so a misconfigured backend surfaces immediately.
- **One-shot claim tokens** are bound to the public_id they were
  issued for (via `secrets.compare_digest`), expire after 60 seconds,
  and are consumed exactly once. Replay fails.

### Added

- 23 new security-focused tests in
  `node/tests/lattice_identity/test_security.py` covering all of the
  above (path traversal, file-size cap, claim tokens, account_id
  validation at both layers, malformed-key error wrapping, mnemonic
  absence from HTTP responses, recover-overwrite refusal).

### Changed

- `src/lattice_identity/__init__.py` re-exports the additional
  helpers (`identity_from_keystore`, `identity_from_mnemonic`,
  `rotate_identity`, `verify_signature`).
- `node/src/routers/lattice_identity_tasks.py` rewritten to:
  - Validate `account_id` before any keystore call.
  - Cap the mnemonic field at 256 chars.
  - Refuse to overwrite an existing identity in `recover`.
  - Issue a one-shot claim token instead of returning the mnemonic
    in `generate` and `rotate`. Add
    `GET /lattice/identity/{account_id}/mnemonic?token=...` as the
    redeem endpoint (placeholder until the keystore grows an
    in-keystore mnemonic store).
  - Best-effort link the generated/rotated identity to the matching
    `Account` record via `AccountManager.edit` (silently no-ops when
    the account does not yet exist).

### Notes

- No CVE entries in the dependency tree (`pip-audit --strict` is
  clean). `bandit` reports 3 low-severity findings (the `assert` is
  gone now, so the remaining three are intentional design choices:
  the `"memory"` CLI sentinel, the `try/except/pass` fall-through in
  `default_keystore`, and the `try/except/continue` patterns).
- Total test count: **65 new tests, all passing** (42 from the
  previous commit, 23 from this one).

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
