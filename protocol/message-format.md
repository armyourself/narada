# Lattice Message Format (Stub)

> Status: **draft / discussion only.**

## Intended message flow

```text
Plaintext
    │
    ▼
Recipient Identity
    │
    ▼
Encryption
    │
    ▼
Ciphertext
    │
    ▼
Lattice Network
    │
    ▼
Ciphertext
    │
    ▼
Recipient
    │
    ▼
Decryption
    │
    ▼
Plaintext
```

Intermediate nodes only see ciphertext. They can route, duplicate-suppress,
and store messages, but they cannot read them.

## Envelope (proposed shape)

The exact byte layout is intentionally not defined yet. A working sketch:

```text
Envelope
├── Header
│   ├── Version           # protocol version
│   ├── Sender Identity    # sender's public-key identity
│   ├── Recipient Identity # recipient's public-key identity
│   ├── Message ID         # unique per message
│   ├── Timestamp
│   ├── Expiry             # optional
│   └── Fragment index/total (optional, for large bodies)
├── Authentication tag    # signs the header
└── Body
    └── Ciphertext        # encrypted to the recipient's public key
```

## Open questions

- Symmetric vs asymmetric envelope: encrypt to a per-message symmetric key,
  then encrypt that key to each recipient's public key (multi-recipient).
- Sign-then-encrypt vs encrypt-then-sign vs sign-the-ciphertext.
- Body format: opaque blob (let the client pick MIME / whatever) vs a
  structured representation.
- Replay protection: nonce, timestamp window, or both.
- Forward secrecy: per-message ephemeral keys, or out of scope for now.
- Attachment handling: inlined, external references, or both.
