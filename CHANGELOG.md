  # Changelog

All notable changes to Narada will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and this project does not yet follow Semantic Versioning.

## [Unreleased]

### Added

- **Narada ↔ SMTP gateway (Phase 5)** under `gateway/gateway/`.
  - `convert.py` -- NaradaBody ↔ RFC822 (`EmailMessage`)
    conversion; preserves subject, sender, to, cc, body_text,
    sent_at; round-trips Narada sender/recipient ids through
    `X-Narada-*` headers.
  - `mapping.py` -- `IdentityMapping`, JSON-backed
    `narada_to_smtp` / `smtp_to_narada` tables; reloadable;
    refuses to forward without a mapping (no open relay).
  - `sender.py` -- `SmtpSender` adapter. Default transport
    wraps the existing Openmail `SMTPManager`; tests pass an
    in-memory transport closure.
  - `receiver.py` -- `ImapReceiver` adapter. Default transport
    wraps the existing Openmail `IMAPManager`; refuses
    anonymous inbound (sender not in the mapping is dropped).
  - `orchestrator.py` -- `Gateway` ties mapping + conversion +
    sender + receiver into two methods: `deliver_outbound`
    (Narada → SMTP) and `poll_inbound` (SMTP → Narada).
  - `errors.py` -- `NoMappingError`, `ConversionError`,
    `SmtpSendError`, `ImapFetchError`.
  - `__main__.py` updated to validate a mapping file with
    `--check`.
  - 19 unit tests under `gateway/tests/` covering conversion
    round-trips, mapping CRUD + reload, sender/receiver
    adapters, and end-to-end outbound + inbound against
    in-memory transports.
  - `gateway/scripts/smoke_phase5.py` round-trips a Narada
    body through the gateway without a live SMTP server.
  - Spec in `protocol/gateway.md`.
  - Concrete specification in `protocol/identity.md` (replaces the prior

### Changed

- `node/src/main.py` now mounts the `narada_identity_tasks` router
  alongside the existing account and mailbox routers. The HTTP API
  surface for existing endpoints is unchanged.
- `AccountManager`'s `Account` / `AccountWithPassword` models gained an
  optional `narada_identity_id` field. No changes to existing fields
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

Aggressive security review of the Narada identity layer landed in this
release. Highlights:

- **Path-traversal vulnerability fixed in `PassphraseKeystore`.** The
  `account_id` is now validated against a safe charset
  (`[A-Za-z0-9._@+-]{1,254}`) at the keystore boundary. Previously an
  HTTP caller could pass `account_id="../../etc/foo"` and have the
  keystore write outside the configured directory. Validation is
  enforced in every `NaradaKeystore` backend, not just the
  filesystem one, as defense in depth.
- **Mnemonic no longer echoed in HTTP response bodies.** The previous
  `/narada/identity/generate` and `/narada/identity/rotate` endpoints
  returned the 12-word recovery phrase in the JSON response, which is
  a total compromise of the keypair if the response is intercepted or
  logged. They now return a one-shot claim token instead. The mnemonic
  must be captured by the desktop client at generation time and is
  never sent over the network. A
  `GET /narada/identity/{account_id}/mnemonic?token=...` redeem
  endpoint is in place; it currently returns a placeholder until the
  keystore grows an in-keystore mnemonic store, and the mechanism
  exists to keep the contract stable.
- **Recover endpoint refuses to silently overwrite an existing
  identity.** Previously, calling `/narada/identity/recover` would
  silently replace the existing seed with the user-supplied mnemonic.
  The user could lose the old identity by mis-typing. Now the
  endpoint refuses to overwrite and tells the caller to delete or
  rotate first.
- **`cryptography` `ValueError` is now caught and re-raised as
  `NaradaIdentityError`.** Bad X25519 public keys (small-subgroup /
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
  `NaradaIdentityError` raise** so the length check survives
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
  `node/tests/narada_identity/test_security.py` covering all of the
  above (path traversal, file-size cap, claim tokens, account_id
  validation at both layers, malformed-key error wrapping, mnemonic
  absence from HTTP responses, recover-overwrite refusal).

### Changed

- `src/narada_identity/__init__.py` re-exports the additional
  helpers (`identity_from_keystore`, `identity_from_mnemonic`,
  `rotate_identity`, `verify_signature`).
- `node/src/routers/narada_identity_tasks.py` rewritten to:
  - Validate `account_id` before any keystore call.
  - Cap the mnemonic field at 256 chars.
  - Refuse to overwrite an existing identity in `recover`.
  - Issue a one-shot claim token instead of returning the mnemonic
    in `generate` and `rotate`. Add
    `GET /narada/identity/{account_id}/mnemonic?token=...` as the
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

## [Unreleased]

### Added

- **Narada protocol MVP** under `node/src/narada/`. The Phase 2
  protocol is now real on loopback HTTP between two Narada nodes
  running on the same machine.
  - `envelope.py` - sealed-and-signed message format. Sign-then-
    encrypt: Ed25519 over a canonical-JSON header, then X25519 ECDH
    + HKDF-SHA256 + ChaCha20-Poly1305 for the body. The recipient
    verifies the signature before doing AEAD work.
  - `transport.py` - `NaradaTransport` ABC + a loopback HTTP
    implementation (`HttpNaradaTransport`). Future transports
    (QUIC, libp2p, relays) plug in behind the same ABC.
  - `directory.py` - `NaradaDirectory` ABC + a JSON-backed
    `LocalContactList` and an `InMemoryDirectory` for tests. The
    directory maps `narada1...` public ids to base URLs.
  - `outbox.py` - persistent JSONL outbox with exponential
    backoff (1m / 5m / 30m / 2h / 12h) and a dead-letter file for
    messages that exceeded the retry budget. Per-account queues.
  - `inbox.py` - receiver-side helper: verify signature, decrypt
    body, persist to a per-account mailbox JSONL with
    `source="narada"`. Replay dedup is in-memory (5-minute TTL).
  - `adapter.py` - the Narada-protocol `MailAdapter` that ties
    the above together. Replaces the Phase B stub in
    `mail_abstraction/narada.py`.
  - `cli/narada_send.py` - manual CLI: `python -m src.cli.narada_send
    <account> <recipient_public_id> --subject ... --body ...`.
  - `routers/narada_protocol_tasks.py` - `POST /narada/inbox`,
    `GET /narada/inbox/{account_id}`, `POST /narada/outbox/retry`.
  - A 30-second background drainer in the FastAPI lifespan that
    flushes every due outbox entry.
- **`OpenmailEmail.source` field** added to the existing Email
  dataclass, defaulting to `"imap"`. The IMAP/SMTP adapter
  (`convert_email`) and the new `NaradaAdapter` (mailbox JSONL)
  both set this so the client UI can tell messages apart later.
- `docs/security/README.md` placeholder stays; the threat model
  is being updated separately.
- 51 new tests covering envelope seal/open, directory, outbox
  (including persistence and dead-letter), inbox (including replay
  dedup), the NaradaAdapter end-to-end (with an in-process
  `InMemoryTransport`), and the HTTP router (including idempotency
  and account_id validation).

### Changed

- `node/src/mail_abstraction/narada.py` removed. The Phase B stub
  is replaced by the full implementation in `node/src/narada/adapter.py`.
- `node/src/mail_abstraction/__init__.py` no longer re-exports
  `NaradaAdapter`; import it from `src.narada` instead.
- `node/src/routers/narada_identity_tasks.py` no longer requires
  any change, but the new router `narada_protocol_tasks` is
  mounted alongside it in `node/src/main.py`.
- `node/src/main.py` now starts a background outbox-drain task in
  the FastAPI lifespan. The task is async-cancelled on shutdown.
- `protocol/message-format.md` promoted from stub to concrete spec.
  Includes the JSON envelope shape, the canonical-JSON recipe, the
  cryptographic recipe, the recipient validation order, and a
  list of properties explicitly deferred to later phases
  (replay persistence, forward secrecy, post-quantum, MIME).

### Notes

- Total test count: **116 new tests, all passing** (65 from
  previous commits, 51 from this one). Existing
  `test_account_manager.py` pre-existing failure is unchanged and
  documented in the prior commit.
- The Phase 2 work is bounded: loopback HTTP only, no P2P discovery,
  no relays, no SMTP/IMAP gateway, no client UI changes. Phase 3+
  builds on this surface.
- No CVE entries in the dependency tree. Three low-severity bandit
  findings remain from the prior security audit (the `"memory"`
  CLI sentinel, the `try/except/pass` fall-through in
  `default_keystore`, the `try/except/continue` patterns). They are
  intentional design choices.

## [0.0.1-alpha0] - initial Openmail release and Narada restructure

- Forked from https://github.com/burakorkmez/openmail. Desktop client
  (SvelteKit + Tauri), self-hosted server (Python / FastAPI), IMAP/SMTP
  support, multiple accounts, unified inbox, advanced search, bulk
  operations, undo actions.
- Restructured repository to the target Narada layout:
  - `app/` → `client/` (desktop client, SvelteKit + Tauri; runnable as before).
  - `server/` → `node/` (Narada node daemon; Python / FastAPI; still speaks
    conventional IMAP/SMTP until the Narada protocol layer lands).
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
  `node/` and to produce `narada_*` artifacts.
- **Bumpversion configuration** (`.bumpversion.toml`) updated to point at
  `client/`, `node/`, and `gateway/` paths; added a `gateway/pyproject.toml`
  version target.
- **Root README rewritten** to describe the new layout and link into
  `protocol/`. The stray ` ```` ` fences from the previous version were
  removed.
- **Makefile** replaced with a small Windows- and POSIX-friendly set of
  targets: `install`, `install-win`, `run-node`, `run-client`, `test-node`.
- `gateway/` package skeleton: future home of the Narada ↔ SMTP/IMAP
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

Narada is forked from
[Openmail](https://github.com/burakorkmez/openmail) and remains
licensed under the Apache License 2.0. See [`LICENSE`](LICENSE).
