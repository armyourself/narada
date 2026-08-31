# Lattice Message Format (Phase 2 MVP)

> Status: **specified.** The on-the-wire JSON shape, the cryptographic
> recipe, and the transport contract are defined here. The
> implementation lives in `node/src/lattice/`.

## Intended message flow

```text
Plaintext (LatticeBody)
    │
    ▼
X25519 ECDH (sender static priv, recipient static pub) -> shared secret
    │
    ▼
HKDF-SHA256(shared, salt, info) -> 32-byte AEAD key
    │
    ▼
ChaCha20-Poly1305(key, nonce, body, aad=canonical_header) -> ciphertext
    │
    ▼
Ed25519 sign over canonical_header bytes (no signature, no ciphertext)
    │
    ▼
JSON envelope {v, sender, recipient, message_id, timestamp, nonce,
               signature, body_ciphertext}
    │
    ▼
LatticeTransport (loopback HTTP for the MVP) -> recipient
    │
    ▼
Recipient: verify signature, decrypt body, persist to mailbox
```

The **signature is over the canonical header**, not the body. The
recipient verifies the signature first and rejects malformed or
untrusted envelopes before doing any AEAD work. This is sign-then-encrypt
from the recipient's perspective.

## JSON envelope

```json
{
  "v": 1,
  "sender_public_id": "lattice1...",
  "recipient_public_id": "lattice1...",
  "message_id": "<uuid4>",
  "timestamp": 1735689600,
  "nonce": "<16 random bytes, base64>",
  "signature": "<64 bytes, base64>",
  "body_ciphertext": "<ChaCha20-Poly1305 ciphertext, base64>"
}
```

Field semantics:

| Field | Type | Notes |
|---|---|---|
| `v` | int | Envelope version. Currently `1`. |
| `sender_public_id` | string | A `lattice1...` public id. The Ed25519 component is used to verify the signature; the X25519 component is used to derive the shared secret. |
| `recipient_public_id` | string | A `lattice1...` public id. The X25519 component is used to derive the shared secret. |
| `message_id` | string | A unique per-message identifier. The sender picks it; the recipient uses it to dedup replays within the timestamp window. |
| `timestamp` | int | Unix seconds. The recipient rejects envelopes outside a 5-minute window. |
| `nonce` | bytes (16) | Random per message. The first 12 bytes are used as the ChaCha20-Poly1305 nonce. |
| `signature` | bytes (64) | Ed25519 signature over the canonical header bytes. |
| `body_ciphertext` | bytes | ChaCha20-Poly1305 ciphertext (includes 16-byte tag). |

## Canonical header

The **header** is the envelope JSON without `signature` and without
`body_ciphertext`. It is encoded with the deterministic-JSON recipe:

- Object keys sorted alphabetically.
- No whitespace: separators are `,` and `:`.
- UTF-8 encoded.

This is the bytes the **signature covers** and the **AAD passed to the
AEAD**. Both sides must use the same canonical encoding or the
signature and AEAD checks will fail.

## Cryptographic recipe

```
shared    = X25519(sender_static_priv, recipient_x25519_pub)
salt      = SHA-256(sender_public_id || ":" || message_id)         # 32 bytes
key       = HKDF-SHA256(shared, salt=salt, info=b"lattice-envelope-v1", length=32)
nonce     = secrets.token_bytes(16)                                # 128 bits
aead_nonce = nonce[:12]                                           # ChaCha20-Poly1305 uses 12 bytes
body_ct   = ChaCha20Poly1305(key, nonce=aead_nonce, plaintext=body, aad=canonical_header_bytes)
signature = Ed25519(sender_ed25519_priv, canonical_header_bytes)
```

- `HKDF-SHA256` with a 32-byte salt binds the AEAD key to the
  `(sender, message_id)` pair, so distinct messages from the same
  sender to the same recipient use different keys.
- The 12-byte AEAD nonce is the first 12 bytes of a 16-byte random
  value. Random 96-bit nonces have a negligible collision risk at
  this scale; 128-bit randomness leaves headroom for future
  transport variants.
- The signature is computed **before** encryption, so the recipient
  can reject tampered envelopes without doing AEAD work.

## Body (plaintext)

`LatticeBody` is a small JSON object. It is encoded with the same
canonical-JSON recipe (sort keys, no whitespace) before encryption,
so the recipient can decode it after `aead.decrypt()` returns.

```json
{
  "subject": "hi",
  "sender": "Alice <alice@example.com>",
  "to": ["Bob <bob@example.com>"],
  "cc": [],
  "body_text": "hello there",
  "sent_at": 1700000000
}
```

| Field | Type | Notes |
|---|---|---|
| `subject` | string | Message subject. |
| `sender` | string | Display string for the sender. Optional. |
| `to` | list[string] | Display strings for the primary recipients. |
| `cc` | list[string] | Display strings for the CC recipients. |
| `body_text` | string | The message body. Plain text only in the MVP. |
| `sent_at` | int | Unix seconds. Optional; the envelope's `timestamp` is authoritative. |

## Recipient validation order

The recipient runs these checks in order. The first failure short-
circuits and returns a typed error to the sender.

1. **Schema.** `LatticeEnvelope.from_dict` parses the JSON and the
   base64 fields. Bad shape → `LatticeEnvelopeError`.
2. **Recipient.** `envelope.recipient_public_id` must equal the
   recipient's local public id. Mismatch → reject.
3. **Version.** `envelope.v` must equal `ENVELOPE_VERSION` (currently
   `1`). Mismatch → reject.
4. **Timestamp window.** `|now - envelope.timestamp|` must be within
   `max_timestamp_skew_seconds` (default 300). Mismatch → reject.
5. **Signature.** Ed25519 verify over the canonical header with the
   sender's public key. Mismatch → reject.
6. **Ciphertext.** ChaCha20-Poly1305 decrypt with AAD = canonical
   header. Tag mismatch → reject.
7. **Body JSON.** Decode the plaintext as UTF-8 + JSON; if it is not
   a JSON object → reject.

After all checks pass, the recipient records the `message_id` in a
short-lived dedup set (default TTL 5 minutes) so that any retry from
the sender within the window is treated as a no-op.

## Out of scope (Phase 2 MVP)

- **Replay protection beyond the timestamp window.** A signed envelope
  can be replayed forever after the timestamp window expires. The
  MVP trusts the 5-minute window; a real implementation will need
  per-recipient "seen message_id" persistence and rotation.
- **Compaction.** The JSON envelope is verbose. Future phases may
  switch to a binary encoding (CBOR / protobuf).
- **Forward secrecy.** Each (sender, recipient) pair reuses the same
  static X25519 key. A per-message ephemeral key (`X25519(ephemeral,
  recipient_static)` followed by a sender-asserted DH ratchet) is
  not in the MVP.
- **Post-quantum.** The MVP is X25519 + Ed25519. A migration path
  through a hybrid KEM (e.g. X25519 + ML-KEM-768) is part of Phase 6
  (Protocol Stabilization).
- **Body parsing.** `LatticeBody` is a flat JSON object. MIME,
  attachments, and threading will come in a later phase.
