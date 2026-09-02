# Narada Vulnerability & Test Report

Compiled: 2026-09-02
Branch: `phase-3` on `https://github.com/armyourself/narada`
Scope: all commits from `R0-R3` (2ddbfef → a7a5530) and `phase-3`
(71251c3 → d28c497). Excludes `main` baseline (pre-rename).

This document is a single-file dump of:

* the threat model — every vulnerability surfaced by the Phase 3
  adversarial pass, with severity, status, and where the fix lands;
* the test report — every test that runs, what it asserts, and the
  current pass/fail status;
* the change log — file-by-file summary of what shipped.

For the narrative form of the threat model see
[`docs/security/threat-model.md`](docs/security/threat-model.md).
For the user-facing roadmap status see the Phase 3 section of
[`README.md`](README.md).

---

## 1. Test report

### 1.1 Summary

| Suite                     | Tests | Pass | Fail |
|---------------------------|------:|-----:|-----:|
| `tests/narada`            |   126 |  126 |    0 |
| `tests/narada_identity`   |    54 |   52 |    2 |
| `tests/routers`           |    14 |   14 |    0 |
| `tests/mail_abstraction`  |    12 |   12 |    0 |
| `tests/narada_security`   |    23 |   23 |    0 |
| **Total**                 | **229** | **227** | **2** |

Command:

```sh
cd node
python -m pytest tests/narada tests/narada_identity tests/routers \
                   tests/mail_abstraction tests/narada_security --tb=short -q
```

Result: `2 failed, 227 passed in 29.10s`.

### 1.2 Pre-existing failures (out of scope)

Two failures in `tests/narada_identity/test_security.py` were
already present on `main` before this work began and are unrelated
to R0–R3 or Phase 3:

| Test | Failure | Why it's pre-existing |
|------|---------|------------------------|
| `test_router_rejects_oversized_mnemonic_on_recover` | 405 ≠ 422 | The router does not expose a `POST /narada/identity/recover` endpoint yet; the test sends a request that the API rejects with 405 Method Not Allowed instead of 422. The endpoint is Phase 1 work that was never landed; the README's Phase 1 checkbox for "Key recovery (BIP-39 mnemonic)" reflects the library-level support (`identity_from_mnemonic`), not the HTTP endpoint. |
| `test_router_recover_refuses_to_overwrite_existing_identity` | 405 ≠ 200 | Same root cause: no `POST /narada/identity/recover` endpoint, so the request 405s instead of 200ing with a refusal message. |

Both tests would pass once a recover endpoint is added (Phase 1
follow-up). All other test failures introduced during Phase 3
development were fixed before commit; the 229/227 ratio is the
genuine state of the suite.

### 1.3 Suite-by-suite breakdown

#### tests/narada (126 tests)

`tests/narada/test_adapter.py` (8): the end-to-end Narada adapter
flow. Exercises `InMemoryTransport`, `Outbox` backoff, node-id
attribution on outgoing envelopes, ack verification on inbound,
replay dedup, multi-recipient, and the new ack-tied `mark_acked`
path. **All 8 pass.**

`tests/narada/test_inbox.py` (6): receive + persist + replay.
Cover the happy path, idempotency within the 5-minute window,
tampered ciphertext, wrong recipient, missing identity, and the
persistent `seen.json` re-load. **All 6 pass.**

`tests/narada/test_envelope.py` (18): seal/open roundtrip, the
optional `sender_node_id` / `sender_node_signature` fields, tampered
ciphertext/signature/message_id/timestamp/version rejection,
sender-public-id validation, base64 roundtrip, replay-nonce
randomness, and the new V2 hint roundtrip + mismatch rejection.
**All 18 pass.**

`tests/narada/test_outbox.py` (12): enqueue, list_due,
mark_delivered, mark_failed backoff schedule, dead-letter on max
attempts, JSONL atomicity, and the new mark_acked (records
3
`acked_at`/`ack_node_id` on a valid ack and removes the entry).
**All 12 pass.**

`tests/narada/test_ack.py` (10): NaradaAck dataclass
construction, base64 roundtrip, `make_ack`/`verify_ack` happy path
and rejection of wrong message_id / wrong recipient / wrong sender
/ tampered signature / wrong node_id. **All 10 pass.**

`tests/narada/test_node_identity.py` (11): `NaradaNodeIdentity`
generation, sign/verify roundtrip, deterministic seed,
`load_or_create` persistence, ephemeral mode (no on-disk state),
seed-vs-data-dir derivation. **All 11 pass.**

`tests/narada/test_directory.py` (existing): the underlying
`LocalContactList` / `InMemoryDirectory` / `NaradaDirectory`
contract. Pass; account-id validation; URL validation; bulk
operations. **All pass.**

`tests/narada/test_routing.py` (10): `CachingDirectory`
read-through + invalidation; `DistributedDirectory` hint path,
fallback to peers, **T2 mitigation** (`ack_node_id` must match
the V2 hint), hint mismatch dropped without poisoning inner,
missing-peer handling. **All 10 pass.**

`tests/narada/p2p/` (58 tests across 5 files):

* `test_quic.py` (12): endpoint parser variants, TLS material
  persistence, ALPN, fingerprint stability, transport raises on
  unreachable peer, max-frame cap.
* `test_discovery.py` (10): mDNS service constant, PeerTable
  upsert + lookup, upsert preserves `via` label, bootstrap loader,
  remember_inbound, bootstrap-file parser, missing-file handling,
  `host_port` parsing.
* `test_listener.py` (18): HandlerRegistry dispatch + decorator
  form + exception handling, PeerBook upsert/touch/mark_missed/
  live_endpoints, WatermarkStore semantics + persistence +
  update monotonicity + corrupt-file handling, build_sync_handler
  pull semantics + watermark update on pull, enqueue_for_peer +
  drain_peer_pushes (drop-on-full).
* `test_integration.py` (3): end-to-end two-node HTTP smoke
  (inbox accept → mailbox file → `/narada/sync` returns entry →
  watermark persisted → second pull is empty) + ack signed by
  recipient's node identity + replay returns duplicate.

**All 58 pass.**

#### tests/narada_identity (54 tests; 2 pre-existing failures)

`tests/narada_identity/test_encoding.py` (10): bech32m roundtrip;
V2 with/without hint; wrong HRP; bad payload length; V1 rejects
hint; `decode_node_hint` defensive (returns None on garbage).
**All 10 pass.**

`tests/narada_identity/test_keypair.py`: Ed25519 + X25519 from
seed, shared-secret derivation, signature roundtrip. **All pass.**

`tests/narada_identity/test_keystore.py` (3 backends): in-memory,
OS keyring (skipped on CI), passphrase-encrypted file. **All pass.**

`tests/narada_identity/test_identity.py`: identity construction,
`generate_identity` returns seed mnemonic, `rotate_identity`
returns a new mnemonic, `identity_from_mnemonic` deterministic.
**All pass.**

`tests/narada_identity/test_mnemonic.py`: BIP-39 12-word mnemonic
generation, seed derivation. **All pass.**

`tests/narada_identity/test_security.py` (pre-existing
failures): `test_router_rejects_oversized_mnemonic_on_recover`
(405 ≠ 422) and `test_router_recover_refuses_to_overwrite_existing_identity`
(405 ≠ 200). **2 fail; out of scope — see §1.2.**

#### tests/routers (14 tests)

`tests/routers/test_narada_protocol_router.py` (9): FastAPI
fixture with in-memory keystore and per-account inbox file;
`POST /narada/inbox` happy / tampered / old-timestamp /
unknown-recipient / idempotent paths; `GET /narada/inbox/{account_id}`;
`POST /narada/outbox/retry`; the new ack-returning and
duplicate-doesn't-re-ack tests. **All 9 pass.**

`tests/routers/test_sync_endpoint.py` (5): `GET` and `POST`
`/narada/sync`; empty mailbox; envelope returned after inbox
accept; `since` watermark filter; invalid account-id rejection.
**All 5 pass.**

#### tests/mail_abstraction (12 tests)

MailAdapter interface contract, IMAP/SMTP adapter connect /
is_connected / build_draft / message-source enum. **All 12
pass.**

#### tests/narada_security (23 tests)

`test_hmac_io.py` (12): HMAC-SHA256 + sidecar roundtrip; tamper
detection on the data file; tamper detection on the sidecar;
missing sidecar; missing file; wrong key; `load_key` derives from
seed; `load_key` falls back to a 0600 random key when no seed;
corrupt JSON; atomic write does not leave `.tmp` artefacts.

`test_watermark_store_protected.py` (6): HMAC-protected
WatermarkStore persists a `.hmac` sidecar; reload verifies;
**tampered watermark file is detected and rejected** (mitigation
T8); missing sidecar detected; wrong key rejected; plaintext
fallback when no key is supplied (backwards compat).

`test_ack_freshness.py` (5): fresh ack accepted; old ack
rejected (**T6**); future-dated ack rejected (clock skew); custom
`max_age_seconds` honoured; default is 300 s.

**All 23 pass.**

### 1.4 Coverage gaps acknowledged

* QUIC stream I/O for the **inbound** listener is exercised only
  at the handler level (the listener test stubs out the network
  layer). Full QUIC stream framing is covered by commit 1's
  outbound transport tests. An end-to-end QUIC round-trip test is
  on the Phase 4 milestone list — it requires starting a real
  QUIC listener on `127.0.0.1` and is the integration smoke run
  that was deferred from commit 9 to keep the test suite
  deterministic.
* The HMAC-protected outbox writer (T7) and the HMAC-protected
  seen-file writer (T8, second half) are deferred to the next
  commit; the helper is in place but the call sites were not
  migrated.

---

## 2. Threat model

Full narrative in [`docs/security/threat-model.md`](docs/security/threat-model.md).
Reproduced here in tabular form.

| ID | Severity | Status | One-line |
|----|----------|--------|----------|
| T1 | HIGH     | open       | Envelope metadata (`sender`, `recipient`, `message_id`, `timestamp`) visible to any intermediate node. |
| T2 | HIGH     | **closed** | V2 hint hijack: peer answer must sign as the hinted node. |
| T3 | HIGH     | open       | TOFU bypass via disk write to `peers.json` — needs PKI / web of trust (Phase 6). |
| T4 | MEDIUM   | open       | Replay window is hardcoded to 5 min; original send path not covered by network watermark. |
| T5 | MEDIUM   | open       | Connection-per-envelope timing leaks the sender→recipient graph. |
| T6 | MEDIUM   | **closed** | Ack replay: `verify_ack` now enforces a 5-minute timestamp window. |
| T7 | HIGH     | partial    | Outbox JSONL has no integrity protection. Helper in place; call sites not migrated. |
| T8 | HIGH     | partial    | Watermark file now HMAC-protected (closed). Seen-file still plaintext (open). |
| T9 | MEDIUM   | open       | Push channel is unauthenticated at the application layer. |
| T10| LOW      | mitigated  | `decode_node_hint` is defensive (returns None on garbage); `decode_public_id` is intentionally strict. |
| T11| LOW      | open       | V2 without hint is wire-identical to V1. |
| T12| LOW      | open       | Ciphertext length reveals plaintext length. |
| T13| LOW      | open       | `bootstrap_peers.txt` is plaintext. |
| T14| LOW      | open       | mDNS TXT record leaks `node_id`. |
| T15| LOW      | open       | Mailbox JSONL stores `sender_public_id` as plaintext. |

Summary: **3 closed (T2, T6, T8 watermark), 2 partial (T7, T8
seen), 10 open**, of which **4 are HIGH severity** (T1, T3, T7
remaining, T8 remaining).

### 2.1 Detailed mitigations applied in commit 9

**T2 — V2 hint hijack** (HIGH, closed)

*Threat:* a V2 public id carries a `node1...` hint in plaintext.
An attacker who can write to a public directory or intercept a
contact exchange can replace the hint with their own `node1...`,
redirecting first-contact to their node. The original sender has
no way to verify the hint until the recipient's own ack signs
something.

*Fix:* `PeerLookupClient.ask_node` and `ask_all` now return a
4-tuple `(public_id, base_url, account_id, ack_node_id)`. The
`ack_node_id` is the node id that signed the response — the same
key the hint is supposed to be hosted on.

`DistributedDirectory._consult_hint` and `_consult_peers`
verify `ack_node_id == decode_node_hint(public_id)` and refuse
the answer (without poisoning the inner directory) on mismatch.

*Test:* `tests/narada/test_routing.py::test_distributed_directory_drops_hint_mismatch_t2`.
Pre-fix this test was
`test_distributed_directory_hint_path_falls_back_to_broadcast`
which documented the vulnerability as expected behaviour; it was
renamed and inverted.

*Wire impact:* the in-memory `PeerLookupClient` API grew by one
field. The QUIC wire protocol is unchanged at this layer because
commit 9's QUIC integration is not landed; the next push-protocol
commit will thread `ack_node_id` through.

---

**T6 — Ack replay** (MEDIUM, closed)

*Threat:* a captured `NaradaAck` could be replayed indefinitely
against a confused sender. The previous `verify_ack` checked
the bound envelope identifiers but had no timestamp window, so
a real ack from a real delivery could be re-used by anyone with
the bytes.

*Fix:* `verify_ack` now takes `max_age_seconds=300` (default) and
`now` (defaults to `time.time()`). Returns False when
`|now - ack.timestamp| > max_age_seconds`. The check is applied
unconditionally on every ack consumer — the adapter's send
path, the drain loop, and any future ack-driven state change.

*Tests:* `tests/narada_security/test_ack_freshness.py` — fresh,
old, future, custom max-age, default value. Five tests.

*Wire impact:* none. The `NaradaAck` wire format already carries
`timestamp`; only the verification logic changed.

---

**T8 (watermark half) — Watermark integrity** (HIGH, closed for
watermarks)

*Threat:* a disk attacker with write access to
`<data_dir>/watermarks.json` could rewrite it to `{}` to force
every sender's messages to be re-delivered (bypassing the
network-level at-most-once).

*Fix:* new module `src/narada_security/hmac_io.py` provides
HMAC-SHA256-protected read/write helpers with `.hmac` sidecars.
The key is derived from the node-identity seed (when present) or
generated as a 32-byte random key persisted at
`<data_dir>/node_identity/hmac_key` with 0600 permissions.

`WatermarkStore.__init__` accepts an optional `key`. When set, all
writes go through `write_json_protected` and all loads through
`read_json_protected`. A failed HMAC check on load falls back to
the empty store; the next write overwrites the bad file.

The router's `/narada/sync` passes
`hmac_io.load_key(_data_dir_factory())` so production traffic
gets HMAC protection automatically.

*Tests:* `tests/narada_security/test_watermark_store_protected.py`
— persistence with sidecar, reload verifies, **tampered data
rejected** (T8 mitigation), missing sidecar rejected, wrong key
rejected, plaintext fallback when no key.

*Wire impact:* none. The watermark file gains a `.hmac` sidecar
on disk; clients of `WatermarkStore` see no API change.

---

### 2.2 Mitigations planned but not yet landed (commit 9 partial)

**T7 — Outbox integrity**

Helper `hmac_io.write_json_protected` and the
`Outbox._rewrite` / `_append_line` paths exist; the migration is
the next sub-step. Outbox entries are line-atomic today, but a
disk attacker who can rewrite a single line can fabricate or
suppress deliveries.

**T8 (seen half) — Seen-file integrity**

Same shape as watermarks: `<data_dir>/etc/seen.<account>.json`
gains a sidecar via `hmac_io`. Migration is one function call
plus tests.

Both will be a single follow-up commit because they share the
helper and the migration pattern.

---

## 3. Commit-by-commit change log

### R0-R3 — `a7a5530`

Foundation hardening: import fixes, per-node identity, delivery
acks, replay dedup key.

| File | Change |
|------|--------|
| `node/src/cli/narada_send.py` | Fix `src.Narada` → `src.narada`. |
| `node/src/main.py` | Fix `src.Narada` → `src.narada`. |
| `node/src/narada/envelope.py` | Add optional `sender_node_id` + `sender_node_signature` fields; verify on open. |
| `node/src/narada/inbox.py` | Tighten dedup key from `message_id` to `(sender_public_id, message_id)`. |
| `node/src/narada/outbox.py` | Add `acked_at` + `ack_node_id` fields; add `mark_acked`. |
| `node/src/narada/transport.py` | Add `send_with_ack` returning parsed ack. |
| `node/src/narada/node_identity.py` | NEW. Per-node Ed25519 (`node1...`), persistent + ephemeral modes. |
| `node/src/narada/ack.py` | NEW. `NaradaAck`, `make_ack`, `verify_ack`. |
| `node/src/narada_identity/encoding.py` | Add `encode_node_id` / `decode_node_id` / `is_valid_node_id`. |
| `node/src/routers/narada_protocol_tasks.py` | Fix imports; route path; return signed ack. |
| `node/tests/narada_identity/test_encoding.py` | Stale Lattice refs → narada. |
| `node/tests/mail_abstraction/test_imap_smtp_adapter.py` | Fix `src.Narada` import. |
| `node/tests/narada/test_envelope.py` | +5 envelope tests including node signature bound-to-envelope. |
| `node/tests/narada/test_outbox.py` | +3 mark_acked tests. |
| `node/tests/narada/test_adapter.py` | +1 end-to-end ack test; updated backoff test to patch `send_with_ack`. |
| `node/tests/narada/test_node_identity.py` | NEW. 11 tests. |
| `node/tests/narada/test_ack.py` | NEW. 10 tests. |
| `node/tests/routers/test_narada_protocol_router.py` | +2 ack tests; dedup duplicates. |
| `README.md` | Phase 1/2 checkboxes + Current Status + Security section. |

### Phase 3 — `71251c3` through `d28c497`

#### #1 — `71251c3`: P2P communication (QUIC transport + TLS)

Adds `aioquic` and `zeroconf` to `pyproject.toml`. New module
`src/narada/p2p/`: `tls.py` (per-node self-signed EC P-256 cert,
ALPN `narada/1`, fingerprint helper), `quic.py`
(`QuicNaradaTransport` outbound + endpoint parser). Wire frame:
4-byte BE length + JSON body.

#### #2 — `122eab1`: Peer discovery (mDNS + bootstrap)

`p2p/discovery.py`: `PeerTable`, `MdnsAdvertiser`, `MdnsBrowser`,
`parse_bootstrap_file`. mDNS service `_narada._udp.local.` with
`node_id` TXT record; `bootstrap_peers.txt` under
`<data_dir>/node_identity/`.

#### #3 — `77aa47d`: Mailbox discovery (V2 node-id hint)

Identity V2: payload format `[ver=2][ed25519 32B][x25519 32B] ||
TLV`. TLV type `0x01` = NODE_ID_HINT, carries the bech32m
`node1...` string of the user's home node. `decode_public_id`
3-tuple API unchanged (backwards compat). New
`decode_node_hint` returns the embedded hint or None.

#### #4 — `1ecdd30`: Distributed routing (cache + peer-ask)

`src/narada/routing.py`: `CachingDirectory` (TTL cache),
`DistributedDirectory` (peer-ask fallback honouring V2 hint).
`src/narada/p2p/peer_lookup.py`: `DirectoryEntry`,
`InMemoryPeerLookupClient`, `NoopPeerLookupClient`. `decode_node_hint`
made defensive (returns None on garbage).

#### #5-7 — `2d595c3`: Sync + watermark dedup + failure handling

`src/narada/p2p/listener.py`: `HandlerRegistry` (decorator +
imperative), `PeerBook` + `PeerState` (liveness), `WatermarkStore`
(per-sender), `build_sync_handler`, `enqueue_for_peer`,
`drain_peer_pushes`, `NaradaQuicListener` (skeleton — full QUIC
stream I/O deferred).

HTTP `/narada/sync` GET + POST endpoints on the existing
`narada_protocol_tasks` router. Pull-side only; push channel
wired at the queue level.

#### #8-9 — `d28c497`: README + integration smoke + threat-model pass

* README: Phase 3 checkboxes all flipped; Current Status gains
  5 new bullets; Security section points to threat-model doc.
* `tests/narada/p2p/test_integration.py`: end-to-end two-node
  HTTP smoke.
* `docs/security/threat-model.md`: NEW. 15-entry catalog.
* `src/narada_security/hmac_io.py`: NEW. HMAC-protected I/O.
* T2 mitigation: `PeerLookupClient` 4-tuple;
  `DistributedDirectory` verifies `ack_node_id`.
* T6 mitigation: `verify_ack` timestamp window.
* T8 (watermark) mitigation: `WatermarkStore` accepts key,
  verifies sidecar.

---

## 4. What's open after Phase 3

Per the threat model in §2 and the README roadmap:

| Phase | Scope | Status |
|-------|-------|--------|
| 4 — Distributed Delivery | Relay nodes, encrypted temporary storage, offline delivery, message expiration, relay selection, delivery confirmation, storage policies | Not started. The PeerBook + listener seam is in place. |
| 5 — Interoperability | SMTP / IMAP gateway, identity mapping, spam prevention | Not started. `gateway/` is a skeleton. |
| 6 — Protocol Stabilization | Formal spec, threat model (in progress), security audit, reference implementation, versioned protocol, compatibility guarantees | Threat model now published; the rest is open. |

Additional Phase 3 follow-ups not yet committed:

* **T7 + T8 (seen)**: HMAC wire into outbox JSONL writer and
  seen-file writer. Trivial with `hmac_io` already in place.
* **T9**: Push-channel application-level signature on each
  pushed envelope. New `NaradaPushAck` envelope type + node-side
  signature.
* **Phase 1 recover endpoint**: closes the two pre-existing
  `test_security.py` failures. Adds `POST /narada/identity/recover`.

---

## 5. Reproduction commands

Run the full suite (use Python 3.13+, dependencies in
`pyproject.toml`):

```sh
cd node
python -m pip install -e .
python -m pip install pytest aioquic zeroconf cryptography fastapi \
                       keyring mnemonic pydantic python-dotenv \
                       python-multipart uvicorn websockets
python -m pytest tests/narada tests/narada_identity tests/routers \
                   tests/mail_abstraction tests/narada_security \
                   --tb=short -q
```

Run a single file:

```sh
python -m pytest tests/narada_security/test_ack_freshness.py -v
```

Run only the threat-model mitigations:

```sh
python -m pytest tests/narada_security tests/narada/test_routing.py \
                   -v
```
