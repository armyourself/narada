# Narada Threat Model

This document catalogues the threats a Narada deployment faces as of
Phase 3, commit 9. Each threat is rated `[HIGH]`, `[MEDIUM]`, or
`[LOW]` and tagged with the commit that closed it (`#5-7`, `#9`) or
that defers it (with the phase the fix lands in).

The threat model assumes an adversary with one or more of:

* passive wire access (TLS terminates at the application layer; the
  transport layer's frame length, mDNS service announcements,
  bootstrap file contents, and IP/port pairs are all visible);
* read or write access to the node's data directory;
* control of a peer the node has on its bootstrap list or mDNS
  reachability;
* the ability to spin up a malicious Narada node reachable over
  the network.

## Catalog

### T1 — Metadata leakage  [HIGH, deferred]

The envelope's outer JSON contains `sender_public_id`,
`recipient_public_id`, `message_id`, `timestamp`. Subject and body
are encrypted; metadata is not. Any intermediate node (mDNS peer,
bootstrap relay) sees who talks to whom and when.

Mitigation requires protocol-level padding and dummy-traffic
injection. Deferred to Phase 4.

### T2 — V2 node-id hint hijack  [HIGH, closed in #9]

The V2 public id embeds a `node1...` string. An attacker who can
write to a public directory or intercept a contact exchange can
replace the hint with their own `node1...`, redirecting first-contact
to their node.

Closed in commit 9: `DistributedDirectory._consult_hint` and
`_consult_peers` now require the peer's `ack_node_id` (the node id
that *signed* the response) to match the V2 hint. A peer that
claims to host a recipient but signs as a different node is
silently rejected; the inner directory is not poisoned with the
bad answer. See `tests/narada/test_routing.py:
test_distributed_directory_drops_hint_mismatch_t2`.

### T3 — TOFU bypass via cert reuse  [HIGH, deferred]

The peer pin store (`<data_dir>/node_identity/peers.json`) protects
only against the network attacker, not the disk attacker. With
write access to that file, an attacker can replace the pin and
have their cert accepted on the next connection.

Closing this requires either a CA/PKI or a web-of-trust for node
certs. Deferred to Phase 6 (formal protocol).

### T4 — Replay window is 5 minutes, hardcoded  [MEDIUM, deferred]

The per-recipient replay window at `<data_dir>/etc/seen.<account>.json`
expires after 5 minutes. An attacker that captures an envelope and
replays it > 5 minutes later bypasses the dedup.

The network-level watermark (closed in commit 5/6) covers
sync/push delivery, but the original send path
(`/narada/inbox`) still uses the 5-minute window.

Closing the gap requires either a longer window (with the
resulting memory growth) or a per-account monotonic sequence
number. Deferred to Phase 4.

### T5 — Connection-per-envelope timing leaks  [MEDIUM, deferred]

`QuicNaradaTransport` opens a fresh QUIC connection per envelope.
An observer with packet timing sees bursts of connection attempts
from host A to host B and back. Correlation reveals who is
talking to whom even without seeing content.

Closing this requires connection multiplexing. Deferred to Phase 4.

### T6 — Ack replay  [MEDIUM, closed in #9]

A captured ack can be replayed to a confused sender indefinitely;
the previous `verify_ack` checked `expected_message_id` but had no
timestamp window.

Closed in commit 9: `verify_ack` now rejects acks whose
`timestamp` differs from `now` by more than `max_age_seconds`
(default 300). The check is applied in every ack-consuming
caller, including the adapter's send path and the drain loop.
See `tests/narada_security/test_ack_freshness.py`.

### T7 — Outbox JSONL has no integrity protection  [HIGH, partial in #9]

An attacker with disk access can inject, delete, or modify outbox
entries, suppressing real deliveries or fabricating new ones.

Partial mitigation in commit 9: HMAC-protected file I/O helpers
land in `src/narada_security/hmac_io.py`. The outbox writer is
not yet wrapped; that is the next sub-step in this work.

### T8 — Watermark and seen files lack integrity  [HIGH, partial in #9]

Same as T7 for `<data_dir>/watermarks.json` and
`<data_dir>/etc/seen.<account>.json`. A disk attacker can rewrite
these to `{}` to force re-delivery of every sender's messages.

Closed for watermarks in commit 9: `WatermarkStore` now takes a
`key` and verifies an HMAC-SHA256 sidecar on load. The router's
`/narada/sync` passes the node-identity-derived key. Tampered
files fall back to an empty store; the next write overwrites the
bad file. See `tests/narada_security/test_watermark_store_protected.py`.

The seen-file is not yet protected (next step).

### T9 — Push channel is unauthenticated  [MEDIUM, deferred]

A push frame is delivered with no application-level signature; the
transport layer (QUIC + TOFU pin) is the only authentication. A
peer can push bogus envelopes and the receiver's inbox will
persist them.

Closing requires a push-signing protocol addition (sender-side
node signature on each pushed entry). Deferred to a Phase 3+
follow-up commit.

### T10 — `decode_public_id` raises on malformed input  [LOW, deferred]

`decode_public_id` raises `NaradaIdentityError` on every
malformed input. Speculative callers (directory lookups, hint
extraction) must wrap each call in `try/except` or use
`decode_node_hint`, which is defensive.

Mitigated for hint extraction (commit 4). The full API
(`decode_public_id`) remains strict because the receiver
*should* reject malformed envelopes.

### T11 — V2 without hint indistinguishable from V1  [LOW, deferred]

`encode_public_id(version=V2, node_id_hint=None)` produces the
same payload as `V1` and the decoder returns `(V2, ...)`. The
behaviour is intentional but masks a programming error where V2
was meant to carry a hint.

Deferred; not a security issue per se.

### T12 — Ciphertext length leaks plaintext length  [LOW, deferred]

ChaCha20-Poly1305 ciphertext length reveals plaintext length.
Subject and body sizes are visible to intermediaries.

Mitigation requires padding or batching. Deferred.

### T13 — `bootstrap_peers.txt` is plaintext  [LOW, deferred]

Anyone with disk access reads the list of peers the node connects
to. Combined with T3, useful for targeted attacks.

OS-level file permissions are the only current mitigation.
Encrypted-on-disk bootstrap is deferred.

### T14 — mDNS service name leaks node id  [LOW, deferred]

The mDNS TXT record carries `node_id=<node1...>`. Any LAN
observer learns which nodes are present and their public ids.

Mitigation: do not advertise the node id; instead advertise a
random opaque token and look it up via the bootstrap list or a
DHT. Deferred to Phase 3+.

### T15 — Inbox mailbox leaks sender graph on disk  [LOW, deferred]

The on-disk mailbox JSONL stores `sender_public_id` as plaintext.
A disk attacker reads the social graph of the recipient.

Encrypting the mailbox is deferred.

## Closing summary

| ID | Severity | Status | Landed in |
|----|----------|--------|-----------|
| T1 | HIGH     | open   | Phase 4+   |
| T2 | HIGH     | closed | #9         |
| T3 | HIGH     | open   | Phase 6    |
| T4 | MEDIUM   | open   | Phase 4    |
| T5 | MEDIUM   | open   | Phase 4    |
| T6 | MEDIUM   | closed | #9         |
| T7 | HIGH     | partial | #9 (helper); wrap outbox next |
| T8 | HIGH     | partial | #9 (watermarks); wrap seen next |
| T9 | MEDIUM   | open   | Phase 3+   |
| T10| LOW      | mitigated (hint only) | #4 |
| T11| LOW      | open   | -          |
| T12| LOW      | open   | Phase 4+   |
| T13| LOW      | open   | -          |
| T14| LOW      | open   | Phase 3+   |
| T15| LOW      | open   | Phase 4+   |
