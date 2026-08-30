# Lattice Identity (Stub)

> Status: **draft / discussion only.**

## What an identity is

Conceptually a Lattice identity is the public face of a user (or a node — see
"Node identity" below). It binds together:

- A **public key** used to verify signatures and derive shared secrets.
- A **node identity**: one or more node references where the user can be
  reached (mailbox location, supported transport, etc.).
- **Mailbox information**: how to deliver messages to this identity.
- **Key metadata**: algorithm, creation time, rotation history, expiry.

```text
Identity
├── Public Key
├── Node Identity
├── Mailbox Information
└── Key Metadata
```

The private key never appears in the identity document. It stays with the
user.

## Required properties (initial)

- **Self-authenticating.** Given an identity, you can verify that the public
  key matches the identifier (e.g. a hash or encoding of the key).
- **Self-contained.** No external authority is required to read or verify an
  identity.
- **Rotatable.** A user can publish a new identity that supersedes an old
  one without losing the chain of trust.
- **Recoverable.** A user must be able to recover the identity from a
  separate channel (paper backup, secondary device, social recovery, etc.).
  The recovery mechanism is not specified here.

## Node identity

Nodes also have identities, separate from the human users that operate them.
A node identity is what other nodes authenticate against during the transport
handshake. Operators may run a node on behalf of many users; the user
identity and node identity are intentionally distinct.

## Open questions

- Encoding: base32, base58, did:key, or a custom format?
- Long-form vs short-form identifiers (think email address vs fingerprint).
- How key rotation and recovery interact.
- Whether to embed human-readable aliases or keep identities opaque.
- How to represent a user with multiple devices (sub-identities, device
  signing keys, etc.).
