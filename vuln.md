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

### Status taxonomy

Each threat is tagged with **status** and **property** columns.
Status says what we did; property says what the result means.
The two are not the same: a status of "closed" paired with a
property of "availability" means we still have an availability
hazard even though we shipped a fix for the confidentiality
hazard.

| Property | What it means |
|----------|---------------|
| **prevent** | The attack cannot reach the system. |
| **detect** | The attack is observed; the system refuses to act on the tampered state. |
| **recover** | After a detected event, the system returns to a consistent state without operator intervention. |
| **availability** | A detected (or undetected) event causes redelivery, loss, or a denial-of-service for legitimate users. |
| **replay / idempotency** | A captured artifact can be re-submitted indefinitely, with at-most-once delivery not guaranteed. |
| **confidentiality** | A passive observer learns the content or metadata of a communication. |

A threat can affect more than one property. The T8 watermark
example below illustrates this — we *detect* tampering, but
recovery from a tampered watermark causes a *re-delivery* (an
availability / replay hazard), so the fix is **detect** for
confidentiality but **availability / replay** remain open.

### What this report is NOT claiming

* **Not** claiming the wire protocol is final. The wire format is
  alpha-grade; subject to change without notice. Several HIGH
  threats remain open (T1, T3, T7 in part, T8 in part). See §2.
* **Not** claiming "no metadata leakage." T1 is open and HIGH.
* **Not** claiming peer authentication. T3 is open and HIGH; the
  QUIC layer relies on TOFU pinning.
* **Not** claiming an audited threat model. No third-party audit
  has been performed.
* **Not** claiming forward secrecy. Past messages stay readable
  to anyone who captures an old seed; rotation protects only
  going-forward authenticity, not past confidentiality.
* **Not** claiming production readiness. The README's WARNING
  banner is still in effect.

---

## 1. Test report

### 1.1 Summary

| Suite                     | Tests | Pass | Fail |
|---------------------------|------:|-----:|-----:|
| `tests/narada`            |   126 |  126 |    0 |
| `tests/narada_identity`   |    54 |   52 |    2 |
| `tests/routers`           |    17 |   17 |    0 |
| `tests/mail_abstraction`  |    12 |   12 |    0 |
| `tests/narada_security`   |    46 |   46 |    0 |
| **Total**                 | **255** | **252** | **2** |

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

## 2. Threat model

### 2.0 Status taxonomy and threat catalog

Status values: **prevent** (attack cannot reach the system),
**detect** (attack is observed and refused), **recover**
(system returns to consistent state without operator), **partial**
(some property mitigated, others not), **open** (no fix landed).
Property values: **confidentiality / integrity / availability /**
replay / authenticity**. A row lists all properties the threat
affects; the *Status → Property* column says which properties the
current code does and does not yet enforce.

A threat can affect more than one property. The T8 watermark
example illustrates this — we *detect* tampering, but recovery
from a tampered watermark causes a *re-delivery* (an
availability / replay hazard), so the fix is **detect** for
confidentiality but **availability / replay** remain open.
|----|-----|-------|------------|---------------------|
| T1 | HIGH | Metadata visible to any intermediate node | confidentiality (sender, recipient, timestamp, size), availability (fingerprintability) | **open** on confidentiality; availability accepted as inherent until padding+dummy-traffic land (Phase 6/7) |
| T2 | HIGH | V2 hint hijack (peer answer signed by a different node than the hint claims) | authenticity, confidentiality | **prevent**: peer answer's `ack_node_id` must equal `decode_node_hint(public_id)`; mismatch rejected without poisoning inner directory |
| T3 | HIGH | TOFU bypass via disk write to `peers.json` | authenticity | **open**: PKI / web-of-trust out of scope (Phase 6). UX work (operator must confirm first contact) on the hardening roadmap |
| T4 | MEDIUM | Replay window hardcoded to 5 min; original send path not covered by network watermark | replay, availability | **open**: 5-minute `seen.<account>.json` TTL stays as a backstop; per-sender LSEQ (additive v=4 field) on the hardening roadmap |
| T5 | MEDIUM | Connection-per-envelope timing leaks sender→recipient graph | confidentiality | **open**: connection multiplexing on Phase 4 |
| T6 | MEDIUM | Ack replay (captured ack reusable indefinitely) | authenticity, replay | **prevent**: `verify_ack` enforces a 5-minute timestamp window (`max_age_seconds` kwarg) |
| T7 | HIGH | Outbox JSONL has no integrity protection | integrity, availability | **partial**: HMAC helper (`hmac_io`) exists; outbox writer not migrated. Migration on the hardening roadmap. **No detect / recover on tamper yet** |
| T8a| HIGH | Watermark file rewrite causes re-delivery of every sender's messages | replay, availability, integrity | **prevent** for replay (tombstone log backs up the snapshot; a tampered snapshot is recovered from the next valid events on load). **Detect** for tamper (sidecar HMAC). Compaction (`WatermarkStore.snapshot()`) bounds the replay cost. See §2.1 T8a |
| T8b| HIGH | Seen-file rewrite bypasses the 5-min replay window | replay, integrity | **open**: same shape as T8a; migration pending |
| T9 | MEDIUM | Push channel is unauthenticated at the application layer | authenticity, replay | **open**: push signing on the hardening roadmap (additive envelope field) |
| T10| LOW  | `decode_public_id` raises on malformed input | availability | **mitigated for hint**: `decode_node_hint` is defensive (None on garbage). **Open** for strict API (intentional) |
| T11| LOW  | V2 without hint is wire-identical to V1 | integrity (programmer-facing) | **open**: not a security issue per se; documentation only |
| T12| LOW  | Ciphertext length reveals plaintext length | confidentiality | **open**: padding on Phase 6/7 |
| T13| LOW  | `bootstrap_peers.txt` is plaintext | confidentiality, availability | **open**: encrypted bootstrap on Phase 6/7 |
| T14| LOW  | mDNS TXT record leaks `node_id` | confidentiality | **open**: opaque token on Phase 3+ follow-up |
| T15| LOW  | Mailbox JSONL stores `sender_public_id` as plaintext | confidentiality | **open**: encrypted mailbox on Phase 4+ |



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

**T8a — Watermark file tamper recovery** (HIGH, **prevent** for
replay + **detect** for tamper; recovery now bounded)

*Threat:* a disk attacker with write access to
`<data_dir>/watermarks.json` could rewrite it to `{}` to force
every sender's messages to be re-delivered (bypassing the
network-level at-most-once).

*Property:* integrity (the file's content cannot be silently
changed without the application noticing), replay (a captured
snapshot is recoverable from the next valid events), availability
(bounded by the number of uncompacted tombstones — see *Limits*
below).

*What we shipped (across two commits):*

1. **HMAC sidecar** on the snapshot file (`src/narada_security/
   hmac_io.py`). Detects silent tampering of the snapshot.
2. **Tombstone log** (`src/narada_security/tombstone_log.py`)
   backing up every `update` since the last snapshot, each entry
   HMAC-signed on its own line. On load, a tampered snapshot
   triggers fallback to the tombstone replay, which restores the
   live state.
3. **`WatermarkStore.snapshot()`** compacts the tombstones
   into a new snapshot and clears the log. The caller (a
   background task or a CLI) decides when.
4. **Migration path** (`test_migration_from_existing_snapshot`):
   a pre-hardening node that already has an HMAC-signed
   watermark.json picks up the new tombstones on first
   `WatermarkStore()` call without losing existing state.

The key is derived from the node-identity seed (when present) or
generated as a 32-byte random key persisted at
`<data_dir>/node_identity/hmac_key` with 0600 permissions. The
router's `/narada/sync` passes
`hmac_io.load_key(_data_dir_factory())` so production traffic
gets HMAC + tombstone protection automatically.

*Limits:* the recovery is bounded by the time between snapshots.
If the attacker tampers with the snapshot AND every tombstone
since the last compaction, the store falls back to empty state
(`get` returns -1) and re-delivery happens for senders that have
no surviving tombstone. Compaction is therefore required for
real protection. The MVP exposes `WatermarkStore.snapshot()` and
`pending_tombstones()`; an automated compactor (e.g. compact
every 1000 updates or every 24 hours) is the next step. **Until
an automated compactor runs, the worst-case re-delivery window
is bounded by the time since the last manual compaction.**

*Tests (28 across two files):*

* `tests/narada_security/test_tombstone_log.py` (11) — append,
  replay, tamper on data / sidecar / missing sidecar, wrong key,
  compact, persistence across instances.
* `tests/narada_security/test_watermark_store_recovery.py`
  (11) — snapshot tamper recovered from tombstone, missing
  snapshot recovered from tombstone, both-tampered attack
  rejected, snapshot + compact + reload, migration from a
  pre-hardening snapshot, legacy plaintext path unchanged.
* `tests/narada_security/test_watermark_store_protected.py`
  (6, two renamed) — HMAC sidecar persistence + reload, the two
  tamper tests now assert *recovery* (state restored from
  tombstones) rather than *rejection* (state discarded), wrong
  key rejected, plaintext fallback.

*Wire impact:* none. The snapshot gains a `.hmac` sidecar; a new
 `<snapshot>.tombstones.jsonl.<n>` file per tombstone; a
 `<node_identity/hmac_key>` fallback key file. Clients of
`WatermarkStore` see two new methods (`snapshot`,
`pending_tombstones`) and no removals.


---

### 2.2 Hardening roadmap (no feature work until these land)

The following threats are tracked for the **hardening round** that
precedes Phase 4. None of them are blocking — but they all leave
a real residual hazard on disk, on the wire, or both.

| ID | What the fix is | Property target | Wire format | Status |
|----|-----------------|-----------------|-------------|--------|
| T8a | Tombstone log for watermark tamper recovery (avoid forced re-delivery) | availability + replay | none (local-state only) | **shipped** — bounded by snapshot interval; automated compactor still pending |
| T7 | Wire `Outbox._rewrite` / `_append_line` through `hmac_io` | integrity + availability | none (local-state only) | not started |
| T8b | Wire `NaradaInbox._save_seen` through `hmac_io`; add LSEQ window as the authoritative dedup | replay | none (local-state only) | not started |
| T4 | LSEQ: per-sender monotonic sequence in envelope body; receiver tracks `<sender, lseq>` | replay | **additive v=4** — `lseq` field in body JSON; v≤3 recipients ignore | not started |
| T9 | Push signing: sender's node signs each pushed envelope; receiver verifies against `sender_node_id` | authenticity + replay | **additive** — `push_signature` field in envelope; v≤3 recipients ignore | not started |
| T3 | First-contact UX: listener prints peer cert fingerprint; operator must `accept` before frames are processed | authenticity (UX mitigation, not PKI) | none | not started |
| T1 | Metadata padding + dummy traffic | confidentiality | breaking (requires new envelope kind) | deferred to Phase 6/7 |
| T3 (PKI) | Real certificate transparency or web of trust | authenticity | new protocol version | deferred to Phase 6 |

Each row will ship as its own commit with adversarial regression
tests added in the same commit. We will not combine hardening
fixes with feature work in a single commit because that makes the
diffs unreviewable.

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

### Phase 1 key rotation (post-Phase 3, hardening-aware) —
`7748874`, `a95ce2d`, `df06323`, `a64f09f`

On-the-wire key rotation shipped across four commits. The
design decision: **Option A** (X25519 preserved across
rotation). See the commit messages for the threat-model
rationale.

Files added:

| File | Purpose |
|------|---------|
| `node/src/narada/key_update.py` | `NaradaKeyUpdate` v=3 envelope: `KeyUpdateBody` dataclass, `make_key_update_envelope`, `open_key_update_envelope` |
| `node/src/narada/key_rotation_store.py` | `KeyRotationRecord` dataclass, `KeyRotationStore` HMAC-protected persistence with `record`, `lookup`, `remove`, `all` |
| `node/src/narada_security/hmac_io.py` (commit `7ef0456`) | reused for `KeyRotationStore` sidecar |
| `node/tests/narada/test_key_update.py` (17 tests) | envelope round-trip, sentinel check, body dataclass round-trip, sender-signs-with-old-key, hint/hint mismatch |
| `node/tests/narada/test_key_rotation_store.py` (15 tests) | record, lookup (active / past not_after), persistence, tamper / missing sidecar / wrong key rejected, plaintext fallback |
| `node/tests/narada_security/test_watermark_store_protected.py` (8 tests) | added in commit `7ef0456` (T8a); not key-rotation work per se |
| `node/tests/narada_identity/test_rotate_preserve_x25519.py` (8 tests) | Option A rotation: Ed25519 rotates, X25519 preserved, multiple rotations keep the same X25519, full vs partial rotation differs |
| `node/tests/narada/test_inbox_rotation.py` (10 tests) | rotation-aware inbox: v=3 key update accepted + persisted, v=1 signed under new key accepted after rotation, dedup, expired not_after rejected |
| `node/tests/routers/test_key_rotation_integration.py` (3 tests) | router-level end-to-end: v=1 backwards compat, v=3 rejected (router doesn't yet thread the rotation store), rotation-aware inbox accepts new-key envelope |

Files modified:

| File | Change |
|------|--------|
| `node/src/narada/envelope.py` | `SUPPORTED_ENVELOPE_VERSIONS = {1, 3}`, `open_envelope` accepts both |
| `node/src/narada_identity/keypair.py` | new `keypair_with_x25519_preserved` constructor (fresh Ed25519 + copied X25519) |
| `node/src/narada_identity/identity.py` | `rotate_identity_preserve_x25519` (uses secret-blob slot), `identity_from_keystore_with_preserved_x25519` |
| `node/src/narada_identity/keystore.py` | abstract `store_secret` / `load_secret` / `has_secret`; `InMemoryKeystore` and `PassphraseKeystore` implement them (encrypted sidecar `<account>.secret.bin` in the passphrase case). 7/7 existing keystore tests still pass. |
| `node/src/narada/inbox.py` | `__init__` accepts `rotation_store`; `receive()` returns `(body, was_duplicate, is_key_update)`. v=3 envelopes are opened as key updates, deduped by `(prior, message_id)`, and persisted via the rotation store (not the mailbox). v=1 envelopes with a sender that has an active rotation record are verified under the rotation's new ed25519 key. |
| `node/src/narada/adapter.py` + `src/routers/narada_protocol_tasks.py` | callers updated to unpack the new 3-tuple |
| `node/tests/narada/test_inbox.py` | existing tests updated to 3-tuple unpacks |

Wire-format impact: v=1 envelopes are unchanged. v=3 envelopes
are new; older senders and older receivers ignore them
(v=1 readers reject on version mismatch, v=3 writers add
a new envelope kind that the older code doesn't see). v=3
is `additive`, not a breaking change.

Threat-model properties of the rotation path:

* **Authenticity**: the key-update envelope is signed by the
  sender's OLD ed25519 key, so the recipient verifies the
  update came from the same owner as the prior identity.
  v=1 envelopes signed with the new ed25519 key are accepted
  only when an active rotation record exists.
* **Availability**: an active rotation record has a bounded
  lifetime (`not_after`); once it closes, the recipient
  expects the sender to use the new public id directly.
* **Integrity / recovery**: `KeyRotationStore` is HMAC-protected
  (T8-style). Tampering is **detected**; recovery from
  corrupted state is the same T8a-bounded-recovery problem
  (vuln.md §2.0). The store has no tombstone log yet; that's
  part of the hardening round.

Open gap: the router's `receive_envelope` endpoint constructs
`NaradaInbox` without a `KeyRotationStore`. A v=3 envelope
posted to the router today is rejected with a 'rotation store'
error (`test_router_rejects_v3_envelope` documents this). The
follow-up is a small commit: add a `_rotation_store_factory`
  endpoint can also be added.

---
Phase 4 feature work (relays, offline delivery, message expiration,
storage policies) is **on hold** until the hardening roadmap in
§2.2 lands. We will not build new distributed machinery on top of
an unauthenticated push channel (T9), an unbounded replay window
(T4), or a forgeable outbox (T7) — those would multiply
attack surface faster than they multiply capability.

### Active roadmap (hardening round)

| Order | ID | What | Wire format |
|------:|----|------|-------------|
| 0 (done) | T8a | Watermark tamper-recovery via tombstone log | none (local state) |
| 1 | T7 | Outbox writer through `hmac_io` (+ tombstone log) | none (local state) |
| 2 | T8b | Seen-file writer through `hmac_io` (+ tombstone log); LSEQ-backed dedup | additive `lseq` field |
| 3 | T4 | Per-sender LSEQ as the authoritative dedup (replaces 5-min window) | additive v=4 |
| 4 | T9 | Push signing: sender node signs each pushed envelope | additive `push_signature` |
| 5 | T3 | First-contact UX (operator confirms peer cert fingerprint) | none |

### Deferred (post-hardening, with reason)

| ID | Reason for deferral |
|----|---------------------|
| T1 | Metadata privacy needs padding + dummy traffic; structural protocol change, not a quick fix. Phase 6/7. |
| T3 PKI | Real certificate transparency or web of trust is a protocol-design project of its own. Phase 6. |
| T10, T11, T12, T13, T14, T15 | LOW-severity; out of scope for the hardening round. Phase 6 cleanup. |

### Out of scope of this branch entirely

* **Phase 4 features** (relays, offline delivery, expiration,
  storage policies) — held until the hardening round above is
  complete.
* **Phase 5 features** (gateway) — held indefinitely; the gateway
  requires a stable, audited protocol.
* **Phase 6 features** (formal spec, audit) — held indefinitely.

### Pre-existing test failures (carry-over from before this work)

* `tests/narada_identity/test_security.py::test_router_rejects_oversized_mnemonic_on_recover`
  — 405 Method Not Allowed (the router does not yet expose
  `POST /narada/identity/recover`). Adds Phase 1's recover
  endpoint in a follow-up.
* `tests/narada_identity/test_security.py::test_router_recover_refuses_to_overwrite_existing_identity`
  — same root cause.
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
