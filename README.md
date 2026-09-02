<h1 align="center">Narada</h1>

<p align="center">
  Decentralized email infrastructure.
</p>

<p align="center">
  Private. Distributed. User-owned.
</p>

> [!IMPORTANT]
> Narada is **alpha-grade software**. The protocol, architecture, APIs, and
> data formats are subject to change without notice. The cryptographic design,
> threat model, and implementation have not been independently audited.
> It is not currently recommended for production, security-critical, or
> irreplaceable communication.

---

## What is Narada?

Narada is an open-source project exploring a decentralized alternative to conventional email infrastructure.

Traditional email depends on centralized infrastructure:

```text
Alice
  │
  ▼
Alice's Mail Provider
  │
  │
  ▼
Bob's Mail Provider
  │
  ▼
Bob
```

Narada aims to replace this model with a distributed network of independently operated nodes:

```text
              Narada Network

        ┌───────────────┐
        │     Alice     │
        │     Node      │
        └───────┬───────┘
                │
          ┌─────┴─────┐
          │           │
          ▼           ▼
     ┌────────┐  ┌────────┐
     │ Node B │  │ Node C │
     └────┬───┘  └───┬────┘
          │           │
          └─────┬─────┘
                ▼
        ┌───────────────┐
        │      Bob      │
        │     Node      │
        └───────────────┘
```

No single server should be required to operate the entire network.

---

## The Idea

Email is fundamentally a messaging protocol.

Yet modern email infrastructure relies heavily on centralized providers to:

* store mail
* authenticate users
* route messages
* maintain mailboxes
* provide search and synchronization
* control access to infrastructure

Narada explores a different model.

Users operate their own nodes. Nodes communicate with one another. Messages are authenticated and encrypted. Infrastructure can be distributed across independently operated participants.

The goal is not to create another Gmail interface.

The goal is to build the **infrastructure underneath the interface**.

---

# Architecture

Narada is designed as several independent layers.

```text
┌─────────────────────────────────────────────┐
│                 Narada Client              │
│                                             │
│  Inbox · Compose · Search · Accounts        │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│              Mail Abstraction               │
│                                             │
│ send() · receive() · sync() · search()      │
└──────────────────────┬──────────────────────┘
                       │
             ┌─────────┴─────────┐
             │                   │
             ▼                   ▼
      ┌──────────────┐    ┌───────────────┐
      │ IMAP / SMTP  │    │ Narada       │
      │ Adapter      │    │ Protocol      │
      └──────────────┘    └───────┬───────┘
                                  │
                           ┌──────▼──────┐
                           │ Narada     │
                           │ Network     │
                           └─────────────┘
```

The client should not need to know whether a message arrived through conventional email infrastructure or the Narada protocol.

---

# Core Principles

## Decentralization

No single organization should be required to operate the entire network.

Anyone should be able to operate a Narada node.

## User Ownership

Users should control their own:

* identity
* cryptographic keys
* mailbox
* node
* data

## Privacy

Messages should be encrypted before being transmitted through infrastructure that does not need access to their plaintext.

## Minimal Trust

A node should not need to blindly trust other nodes.

The protocol should assume that nodes can fail, disappear, behave incorrectly, or become compromised.

## Resilience

Individual nodes should be allowed to disappear without bringing down the entire network.

Offline users should not necessarily mean undeliverable messages.

## Interoperability

Narada should coexist with existing email infrastructure rather than requiring the entire world to migrate immediately.

---

# Identity

Narada is intended to use cryptographic identities rather than relying exclusively on centralized usernames and passwords.

Conceptually:

```text
Identity
├── Public Key
├── Node Identity
├── Mailbox Information
└── Key Metadata
```

A user's private key remains under the user's control.

The exact identity format and cryptographic architecture are still under development. See [`protocol/identity.md`](protocol/identity.md) for the working draft.

---

# Message Delivery

A Narada message may eventually travel through several independently operated nodes.

```text
Alice
  │
  │ encrypted message
  ▼
Node A
  │
  ▼
Node B
  │
  ▼
Node C
  │
  │ encrypted message
  ▼
Bob
```

Intermediate nodes should only need to transport or temporarily store the message.

They should not require access to its plaintext.

---

# Offline Delivery

A decentralized network still needs to solve the problem that users are not always online.

Narada therefore explores encrypted relay nodes.

```text
Alice
  │
  ▼
Relay A
  │
  ▼
Relay B
  │
  │
  ▼
Bob comes online
  │
  ▼
Message delivered
```

Relay infrastructure may temporarily store encrypted messages until the recipient becomes reachable.

The protocol must eventually define:

* message expiration
* delivery confirmation
* relay selection
* duplicate detection
* storage limits
* node failure
* malicious relay behavior

---

# Conventional Email

Narada is not intended to exist in isolation.

A future gateway could allow communication between Narada and conventional email:

```text
Gmail
  │
  │ SMTP
  ▼
┌─────────────────┐
│ Narada Gateway │
└────────┬────────┘
         │
         │ Narada Protocol
         ▼
   Narada Network
         │
         ▼
   Narada User
```

Likewise, Narada users should eventually be able to communicate with conventional email addresses.

The gateway lives in [`gateway/`](gateway/) and is currently a skeleton; the Narada-side delivery pipeline must land first.

---

# Current Status

Narada currently builds upon an existing self-hosted email client/server architecture.

The inherited application provides functionality including:

* Desktop email client
* Self-hosted server (still speaks conventional IMAP/SMTP)
* IMAP support
* SMTP support
* Multiple accounts
* Unified inbox
* Advanced search
* Bulk operations
* Undo actions

Narada-specific work landed so far (under `node/` and `protocol/`):

* **Mail Abstraction layer** (`node/src/mail_abstraction/`): a single
  `MailAdapter` interface with an IMAP/SMTP adapter and a Narada
  adapter.
* **Cryptographic identity** (`node/src/narada_identity/`,
  `protocol/identity.md`): per-account Ed25519 + X25519 keypair with a
  `narada1...` bech32m public id, 12-word BIP-39 mnemonic recovery,
  and three keystore backends (in-memory, OS keyring, passphrase
  fallback). Exposed via a FastAPI router and a CLI.
* **Narada protocol MVP** (`node/src/narada/`,
  `protocol/message-format.md`): two Narada nodes on the same
  machine can exchange end-to-end encrypted messages over loopback
  HTTP. The envelope is X25519-ECDH-sealed and Ed25519-signed; the
  body is ChaCha20-Poly1305. A persistent outbox with
  exponential-backoff retry handles the recipient being offline.
* **Per-node identity** (`node/src/narada/node_identity.py`): each
  node daemon has its own Ed25519 keypair (`node1...` bech32m id)
  used to attribute envelopes and sign delivery acks. Persistent by
  default (`<data_dir>/node_identity/seed`, 0600), or `ephemeral=True`
  for a fresh keypair per envelope (no linkability across sends).
  Wire-format fields `sender_node_id` / `sender_node_signature` are
  **optional and additive**: older Narada nodes that do not recognise
  them still verify the user-key signature and accept the message.
* **Delivery acknowledgements** (`node/src/narada/ack.py`): a
  successful envelope accept returns a signed `NaradaAck` (Ed25519
  over `(sender_public_id, recipient_public_id, message_id,
  timestamp, status)`) tied to the recipient's node identity. The
  sender's outbox transitions the entry to *acked* and removes it.
  The ack is best-effort: a missing ack still counts as a successful
  delivery, with the outbox entry removed for compatibility with
  pre-R3 nodes.
* **Replay protection** (Narada inbox): an envelope's `(sender,
  message_id)` pair is recorded in a per-recipient dedup window
  (`<data_dir>/etc/seen.<account>.json`, default TTL 5 min) that
  survives process restarts. Re-submissions within the window are
  acknowledged but not re-persisted.
* Peer discovery, distributed routing, relays, and the
  Narada↔SMTP/IMAP gateway are **not yet implemented**. The
  protocol layer above is the seam where they will plug in.

The decentralized protocol is being developed separately from these existing components.

---

# Repository Structure

```text
Narada/
├── client/         # Desktop client (SvelteKit + Tauri)
├── node/           # Narada node daemon (Python / FastAPI; Openmail-derived)
├── gateway/        # Narada <-> SMTP/IMAP bridge (skeleton)
├── protocol/       # Protocol spec, identity format, message envelope (stubs)
├── docs/
│   ├── architecture/   # Installation, roadmap, screenshots
│   ├── protocol/       # Protocol-facing documentation
│   └── security/       # Threat model, audit notes (stub)
├── scripts/        # install.ps1, dev.ps1
├── tools/          # shared build/dev helpers
├── .github/        # CI workflows
├── Makefile
├── LICENSE
└── README.md
```

---

# Roadmap

## Phase 0 — Client Foundation

* [x] Desktop email client
* [x] Self-hosted server
* [x] IMAP
* [x] SMTP
* [x] Multiple accounts
* [x] Unified inbox
* [x] Advanced search
* [x] Bulk operations
* [x] Undo actions

## Phase 1 — Cryptographic Identity

* [x] Generate keypairs
* [x] Secure private-key storage
* [x] Public-key identities
* [x] Identity format
* [x] Identity persistence
* [ ] Key rotation (basic rotate-API only; on-the-wire rotation is Phase 3+)
* [x] Key recovery (BIP-39 mnemonic)

## Phase 2 — Narada Protocol

* [x] Define protocol specification
* [x] Define message format
* [x] Define node identity (per-daemon Ed25519 with `node1...` bech32m id;
      optional `sender_node_id`/`sender_node_signature` fields on envelopes)
* [x] Secure handshake (X25519 ECDH + Ed25519 signature on the canonical header)
* [x] Encrypted transport (ChaCha20-Poly1305 over loopback HTTP)
* [x] Message authentication (Ed25519 signature on canonical header)
* [x] Replay protection: persistent (sender, message_id) window stored on disk per
      recipient (default TTL = 5 minutes); expired entries are reaped on every check
* [x] Delivery acknowledgements (recipient node signs an ack over
      `(sender, recipient, message_id, timestamp, status)`; sender outbox
      transitions to *acked* on valid signature)

## Phase 3 — Distributed Network

* [ ] Peer discovery
* [ ] Peer-to-peer communication
* [ ] Distributed routing
* [ ] Mailbox discovery
* [ ] Message synchronization
* [ ] Duplicate detection
* [ ] Node failure handling

## Phase 4 — Distributed Delivery

* [ ] Relay nodes
* [ ] Encrypted temporary storage
* [ ] Offline delivery
* [ ] Message expiration
* [ ] Relay selection
* [ ] Delivery confirmation
* [ ] Storage policies

## Phase 5 — Interoperability

* [ ] SMTP gateway
* [ ] IMAP gateway
* [ ] Narada → SMTP
* [ ] SMTP → Narada
* [ ] Identity mapping
* [ ] Spam prevention

## Phase 6 — Protocol Stabilization

* [ ] Formal protocol specification
* [ ] Threat model
* [ ] Security audit
* [ ] Reference implementation
* [ ] Versioned protocol
* [ ] Compatibility guarantees

---

# Security

Security is a fundamental part of the protocol.

The intended message flow is:

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
Narada Network
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

**Current security status**

Narada's cryptographic primitives — X25519 for key agreement, Ed25519 for
signatures, ChaCha20-Poly1305 for payload encryption, BIP-39 for mnemonic
recovery, bech32m for public identifiers — are well-known and widely vetted
algorithms. The composition and wire format, however, are **alpha-grade**:

* the formal protocol specification has not been published (Phase 6)
* the threat model has not been published (`docs/security/` is a stub)
* no third-party security audit has been performed
* key rotation is partial (rotate-API exists; on-the-wire rotation is not
  specified yet — Phase 3+)
* replay protection covers a 5-minute window with persistent (sender,
  message_id) dedup; longer-horizon replay and forward secrecy are
  not yet specified
* delivery acknowledgements are best-effort: a missing ack still counts
  as a successful delivery for backward compatibility
* metadata protection is not yet specified

Until those items are closed, treat Narada as a **research-grade reference
implementation**: useful for development, integration work, and protocol
discussion, but not a substitute for an audited messaging system for any
communication whose loss or compromise would cause harm.

---

# Development

Prerequisites:

- Python 3.13+ and [uv](https://github.com/astral-sh/uv) (for the node)
- [Bun](https://bun.sh) and the [Rust toolchain](https://tauri.app/start/prerequisites/) (for the desktop client)

Linux / macOS:

```sh
./install.sh
```

Windows (PowerShell):

```pwsh
pwsh -File scripts/install.ps1
```

Run the node:

```sh
cd node
uv run python -m src.main
```

Run the desktop client:

```sh
cd client
bun run tauri dev
```

Or, on Windows, use the dev launcher to spawn both in separate windows:

```pwsh
pwsh -File scripts/dev.ps1
```

Convenience targets via the included `Makefile`:

```sh
make install      # run install.sh (Linux/macOS)
make run-node     # run the Narada node
make run-client   # run the desktop client
make test-node    # run the node's test suite
```

---

# Contributing

Narada is experimental and architectural decisions are still being made.

Contributions are welcome, particularly around:

* distributed systems
* networking
* cryptography
* protocol design
* storage
* synchronization
* security
* email standards
* client development

Before implementing major protocol changes, review the relevant design documentation and open a discussion where appropriate.

---

# Origin

Narada began as a fork of **Openmail**, an open-source self-hosted email client/server.

The original project provided the foundation for the client and existing email functionality. Narada extends that foundation toward a decentralized communication protocol.

The original project's license and attribution requirements remain applicable to the code derived from it.

See [`LICENSE`](LICENSE) for the applicable license terms (Apache License 2.0). Upstream: <https://github.com/burakorkmez/openmail>.

---

# License

Narada is distributed under the terms of the project's license.

See [`LICENSE`](LICENSE) for details.

---

<p align="center">
  <strong>Narada</strong><br>
  Decentralized email infrastructure.
</p>
