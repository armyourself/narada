# Narada Relay Protocol (Phase 4)

> Status: **specified (Phase 4).** The wire format for relay deposit,
> fetch, drop, and stored-receipt is defined here. The implementation
> lives in `node/src/narada/relay/`.

## Goal

A user is not always online. A node that cannot reach the recipient
should be able to hand the sealed envelope to one or more peers
(**relays**) and have the recipient pull it the next time the
recipient's node is reachable.

```
Alice's node (sender)
    │
    │  relay.deposit(envelope) over QUIC
    ▼
Relay node                  ◄─── Relay cannot read the plaintext.
    │                            It stores ciphertext only.
    │  ... time passes ...
    ▼
Bob's node (recipient)
    ▲
    │  relay.fetch(recipient_public_id) over QUIC
    │
Relay node                  ◄─── Ciphertext returned; envelope AEAD
                               decrypts locally on Bob's node.
```

The envelope already has end-to-end confidentiality
(`protocol/message-format.md`). The relay adds **store-and-forward
durability** without breaking that property.

## Threat model (Phase 4 scope)

The relay is honest-but-curious. It can:

* see `(sender_public_id, recipient_public_id, message_id, timestamp)`
  metadata on envelopes it stores;
* drop, delay, or refuse envelopes;
* attempt to deposit envelopes for recipients that are not its own.

It **cannot**:

* read the body — the body is encrypted to the recipient's X25519
  key (`envelope.body_ciphertext` is opaque to the relay);
* forge a recipient-side `NaradaAck` — that requires the
  recipient's node key.

Out of scope: malicious relays colluding to de-anonymize metadata
(one-hop single-relay does not hide it from the chosen relay; onion
multi-hop is a later phase), censorship of arbitrary senders (relay
selection is local to the sender), and relay-operator denial of
storage (the sender's outbox retries until success).

## Wire surface

Three frame types ride on the existing QUIC listener
(`node/src/narada/p2p/listener.py`):

```jsonc
// sender -> relay: "please hold this for the recipient"
{"type": "relay.deposit",
 "v": 1,
 "envelope": { ...NaradaEnvelope.as_dict()... },
 "expires_at": 1736000000}

// sender -> relay or recipient -> relay: "give me what's mine"
{"type": "relay.fetch",
 "v": 1,
 "recipient_public_id": "narada1...",
 "limit": 64}

// recipient -> relay: "I took mine, drop them by id"
{"type": "relay.drop",
 "v": 1,
 "deposit_ids": ["<uuid>", ...]}
```

Plus a relay -> sender `stored` receipt:

```jsonc
{"type": "relay.stored",
 "v": 1,
 "deposit_id": "<uuid>",
 "recipient_public_id": "narada1...",
 "message_id": "<uuid>",
 "stored_at": 1735689700,
 "expires_at": 1736000000,
 "relay_node_id": "node1...",
 "signature": "<64 bytes, base64>"}
```

The `signature` is Ed25519 over the canonical bytes of the receipt
without `signature`, keyed by the **relay's** node identity. The
sender keeps it as a best-effort proof-of-store; it is **not** a
delivery acknowledgement (that still comes from the recipient).

## Storage model

The relay maintains a per-recipient store, keyed by
`recipient_public_id`. Each deposit is one record:

```json
{
  "deposit_id": "<uuid>",
  "recipient_public_id": "narada1...",
  "envelope": { ... },
  "stored_at": 1735689700,
  "expires_at": 1736000000,
  "size_bytes": 1234
}
```

### Encryption at rest

The relay writes `envelope` to disk under a **per-recipient key**
derived from a relay-side master secret and the recipient's
`narada1...` public id, so a disk attacker who steals the relay's
data directory cannot read envelopes without also compromising the
relay's in-memory master secret:

```
deposit_key   = HKDF-SHA256(relay_master, salt=recipient_public_id,
                           info=b"Narada-relay-v1", length=32)
nonce         = random 12 bytes
ct            = ChaCha20-Poly1305(deposit_key, nonce, envelope_json_bytes,
                                 aad=canonical_receipt_payload)
```

`canonical_receipt_payload` is the bytes the relay's `signature`
covers (so the relay cannot swap the stored body for one it later
signs). The encrypted blob is what lands on disk; the live in-memory
representation may keep the plaintext copy while the relay is
running, but it is re-derived on read so a single code path handles
both the freshly-deposited and the on-disk-decrypted cases.

### TTL and expiry

Each deposit carries `expires_at` (unix seconds). Default TTL:
**604 800 seconds (7 days)**. The relay refuses a deposit whose
`expires_at` is in the past, more than `max_ttl_seconds` in the
future (default 30 days), or whose remaining lifetime would breach
the relay's quota (see below).

Expired entries are reaped:

* **On access** — `relay.fetch` and `relay.drop` skip expired entries
  silently.
* **On a background sweeper** — once per `sweep_interval_seconds`
  (default 5 minutes) the relay walks the store and deletes anything
  whose `expires_at <= now`.

The sweeper uses an HMAC-protected sidecar and tombstone log so a
disk attacker cannot undelete by rewriting the on-disk file (the
pattern follows `node/src/narada_security/watermark_store.py`).

### Quota / storage policies

Per recipient:

* `max_deposits_per_recipient` — default **64**.
* `max_bytes_per_recipient` — default **16 MiB**.

Globally:

* `max_total_deposits` — default **16 384**.
* `max_total_bytes` — default **256 MiB**.

A `relay.deposit` whose addition would breach a cap is refused with
a typed error (`"recipient_quota_exceeded"` or `"relay_quota_exceeded"`).
The sender's outbox retries with backoff. There is no LRU eviction
in Phase 4 — refusing is the policy.

### Replay protection

A `(recipient_public_id, message_id)` pair is recorded for the life
of the deposit. A second `relay.deposit` for the same pair is
accepted (idempotent, returns the existing `deposit_id`) without
counting against quota.

### Persistence

Layout:

```
<data_dir>/relay/
  ├── deposits/<recipient>.jsonl      # encrypted envelopes, one per line
  ├── index.json                     # plain metadata, HMAC-protected
  ├── tombstones.log                 # append-only delete log
  └── receipts/<deposit_id>.bin      # best-effort relay.signed receipts
```

Atomic writes: deposits land at `<recipient>.jsonl.tmp` and are
`os.replace`'d into place. Index writes follow the watermark-store
tombstone pattern.

## Relay selection (sender-side)

The sender's `NaradaAdapter` consults `RelaySelector` in this order:

1. **V2 mailbox-discovery hint.** If the recipient's public id carries
   a `node_id_hint` TLV (`protocol/identity.md`) and the hinted node
   is reachable (`PeerBook.is_reachable(node_id)` returns `True`),
   deposit there.
2. **Peer book fallback.** Otherwise pick a peer from `PeerBook`
   sorted by `(down=False first, last_seen desc, missed_pings asc)`
   and exclude nodes already used in this outbox entry's retry
   budget (`cooldown_seconds`, default 300).
3. **Give up** — return no relay; the outbox keeps retrying the
   direct path.

Selection is deterministic for a given `PeerBook` snapshot, so
sending the same envelope twice does not pick different relays
back-to-back.

## Delivery confirmation (Phase 4)

The **recipient-side** confirmation is unchanged: the recipient's
node pulls from the relay, runs the existing envelope verification
(`protocol/message-format.md` §Recipient validation order), and
returns its existing signed `NaradaAck` over the same transport.
That ack is the source of truth for "the recipient got it".

The **relay-side** confirmation is the `relay.stored` receipt
described above. It is logged and returned to the sender; the
sender's outbox records it as `relay_deposited_at`. A missing
`relay.stored` is not a delivery failure (consistent with README §
Security's "best-effort ack" stance).

## On-the-wire envelope compatibility

A deposit is the existing `NaradaEnvelope.as_dict()` plus
`expires_at`. The relay never sees `body_text`, `subject`, or any
other plaintext field — it only sees the AEAD ciphertext that was
already opaque to it on the wire.

Older (pre-R4) Narada nodes that do not recognise `relay.*` frames
respond with `{"type": "error", "message": "unknown type: relay.deposit"}`.
The sender's outbox treats that as a "this peer is not a relay"
hint and falls through to the next selection candidate.

## Out of scope (Phase 4)

* Multi-hop onion routing (single-hop is enough to prove offline
  delivery).
* Relay reputation, payment, or Sybil resistance.
* Forward secrecy over the relay leg (the AEAD key is per-envelope
  but not ratcheted; the long-term X25519 static key of the
  recipient is reused for both legs).
* Post-quantum relay transport (QUIC with X25519 only).
* Spam filtering at the relay (rate limits per recipient are out of
  scope; the sender's outbox caps retries naturally).
* Recipient privacy against a chosen relay (a relay chosen by hint
  knows the recipient's public id; that is the design trade-off).
