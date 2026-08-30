<h1 align="center">Lattice</h1>

<p align="center">
  Decentralized email infrastructure.
</p>

<p align="center">
  Private. Distributed. User-owned.
</p>

> [!WARNING]
> Lattice is experimental software under active development.
> The protocol, architecture, APIs, and data formats are subject to change.
> It is not currently suitable for production or security-critical communication.

---

## What is Lattice?

Lattice is an open-source project exploring a decentralized alternative to conventional email infrastructure.

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

Lattice aims to replace this model with a distributed network of independently operated nodes:

```text
              Lattice Network

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

Lattice explores a different model.

Users operate their own nodes. Nodes communicate with one another. Messages are authenticated and encrypted. Infrastructure can be distributed across independently operated participants.

The goal is not to create another Gmail interface.

The goal is to build the **infrastructure underneath the interface**.

---

# Architecture

Lattice is designed as several independent layers.

```text
┌─────────────────────────────────────────────┐
│                 Lattice Client              │
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
      │ IMAP / SMTP  │    │ Lattice       │
      │ Adapter      │    │ Protocol      │
      └──────────────┘    └───────┬───────┘
                                  │
                           ┌──────▼──────┐
                           │ Lattice     │
                           │ Network     │
                           └─────────────┘
```

The client should not need to know whether a message arrived through conventional email infrastructure or the Lattice protocol.

---

# Core Principles

## Decentralization

No single organization should be required to operate the entire network.

Anyone should be able to operate a Lattice node.

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

Lattice should coexist with existing email infrastructure rather than requiring the entire world to migrate immediately.

---

# Identity

Lattice is intended to use cryptographic identities rather than relying exclusively on centralized usernames and passwords.

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

A Lattice message may eventually travel through several independently operated nodes.

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

Lattice therefore explores encrypted relay nodes.

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

Lattice is not intended to exist in isolation.

A future gateway could allow communication between Lattice and conventional email:

```text
Gmail
  │
  │ SMTP
  ▼
┌─────────────────┐
│ Lattice Gateway │
└────────┬────────┘
         │
         │ Lattice Protocol
         ▼
   Lattice Network
         │
         ▼
   Lattice User
```

Likewise, Lattice users should eventually be able to communicate with conventional email addresses.

The gateway lives in [`gateway/`](gateway/) and is currently a skeleton; the Lattice-side delivery pipeline must land first.

---

# Current Status

Lattice currently builds upon an existing self-hosted email client/server architecture.

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

Lattice-specific work landed so far (under `node/` and `protocol/`):

* **Mail Abstraction layer** (`node/src/mail_abstraction/`): a single
  `MailAdapter` interface with an IMAP/SMTP adapter and a stub
  Lattice-protocol adapter. The interface is exercised by tests; the
  router migration is the next step.
* **Cryptographic identity** (`node/src/lattice_identity/`,
  `protocol/identity.md`): per-account Ed25519 + X25519 keypair with a
  `lattice1...` bech32m public id, 12-word BIP-39 mnemonic recovery,
  and three keystore backends (in-memory, OS keyring, passphrase
  fallback). Exposed via a FastAPI router and a CLI.
* The decentralized protocol (node-to-node transport, message
  envelope, peer discovery, relays) is **not yet implemented**. The
  adapter and identity pieces are the seam where it will plug in.

The decentralized protocol is being developed separately from these existing components.

---

# Repository Structure

```text
lattice/
├── client/         # Desktop client (SvelteKit + Tauri)
├── node/           # Lattice node daemon (Python / FastAPI; Openmail-derived)
├── gateway/        # Lattice <-> SMTP/IMAP bridge (skeleton)
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
* [ ] Key rotation (basic rotate-API only; on-the-wire rotation is Phase 2+)
* [x] Key recovery (BIP-39 mnemonic)

## Phase 2 — Lattice Protocol

* [ ] Define protocol specification
* [ ] Define message format
* [ ] Define node identity
* [ ] Secure handshake
* [ ] Encrypted transport
* [ ] Message authentication
* [ ] Delivery acknowledgements
* [ ] Replay protection

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
* [ ] Lattice → SMTP
* [ ] SMTP → Lattice
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

However:

> **Lattice is not currently considered secure.**

The cryptographic design, threat model, key management, metadata protection, and protocol security are still being developed.

Do not use experimental Lattice implementations for sensitive communication.

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
make run-node     # run the Lattice node
make run-client   # run the desktop client
make test-node    # run the node's test suite
```

---

# Contributing

Lattice is experimental and architectural decisions are still being made.

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

Lattice began as a fork of **Openmail**, an open-source self-hosted email client/server.

The original project provided the foundation for the client and existing email functionality. Lattice extends that foundation toward a decentralized communication protocol.

The original project's license and attribution requirements remain applicable to the code derived from it.

See [`LICENSE`](LICENSE) for the applicable license terms (Apache License 2.0). Upstream: <https://github.com/burakorkmez/openmail>.

---

# License

Lattice is distributed under the terms of the project's license.

See [`LICENSE`](LICENSE) for details.

---

<p align="center">
  <strong>Lattice</strong><br>
  Decentralized email infrastructure.
</p>
