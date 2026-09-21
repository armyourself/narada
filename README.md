<h1 align="center">Narada</h1>

<p align="center">
  Decentralized email with Nostr transport.
</p>

<p align="center">
  Private. Distributed. User-owned.
</p>

> [!IMPORTANT]
> This is **alpha-grade software**. The architecture, APIs, and data formats
> are subject to change without notice. The cryptographic design, threat model,
> and implementation have not been independently audited.
> Do not use for production, security-critical, or irreplaceable communication.

---

## What is this?

An open-source email application that uses [Nostr](https://nostr.com) as its
decentralized transport layer.

```text
    Email Client
          |
     MailAdapter
          |
       +------+
       |      |
     IMAP    Nostr
     SMTP    Transport
              |
         Nostr Relay Pool
```

The application speaks conventional IMAP/SMTP for traditional email accounts,
and Nostr for decentralized, encrypted messaging -- through a single unified
interface.

---

## Why Nostr?

Nostr is a simple, open protocol for decentralized communication. It provides:

- **Relay network**: messages are published to multiple relays, giving
  redundancy without depending on any single server.
- **Ed25519 identities**: each user has a cryptographic keypair that serves
  as their identity -- no username/password required.
- **End-to-end encryption**: NIP-04 (AES-256-CBC) and NIP-44 (ChaCha20-
  Poly1305) encrypt message content so relays cannot read it.
- **Censorship resistance**: no central authority controls who can publish
  or subscribe.
- **Simple protocol**: JSON messages over WebSocket -- easy to implement,
  easy to audit.

---

## Architecture

```text
┌─────────────────────────────────────────────┐
│              Desktop Client                 │
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
      ┌──────────────┐    ┌──────────────┐
      │ IMAP / SMTP  │    │    Nostr     │
      │ Adapter      │    │   Adapter    │
      └──────────────┘    └──────┬───────┘
                                 │
                          ┌──────▼──────┐
                          │  Nostr      │
                          │  Relay Pool │
                          └─────────────┘
```

The client doesn't need to know whether a message arrived through
conventional email infrastructure or Nostr relays.

---

## Identity

Each user has a Nostr identity -- an Ed25519 keypair:

```text
Identity
├── Public Key (npub1...)
├── Secret Key (nsec1...)
└── X25519 Keys (derived, for encryption)
```

- **Public key** (NIP-01 hex or NIP-19 bech32 `npub1...`) identifies the user.
- **Secret key** (`nsec1...`) is stored locally and never transmitted.
- **X25519 keys** are derived from the Ed25519 seed for NIP-04/NIP-44 encryption.

Identities are generated locally. No registration, no central authority.

---

## Encryption

Two encryption modes are supported:

### NIP-04 (default)

AES-256-CBC with PKCS7 padding. Shared secret derived via X25519 ECDH.
Broadly supported across Nostr implementations.

### NIP-44 (enhanced)

ChaCha20-Poly1305 AEAD. More secure than NIP-04 (authenticated encryption).
Used for application-to-application communication when both endpoints support it.

Both modes derive the shared secret from Ed25519 keys using Curve25519
scalar clamping (SHA-512 hash, first 32 bytes, clamp bits).

---

## Nostr Transport

### Relays

Messages are published to a configurable set of Nostr relays. The relay pool
provides:

- **Multi-relay failover**: if one relay is down, others continue to work.
- **Deduplication**: events from multiple relays are deduplicated by event id.
- **Auto-reconnection**: exponential backoff on disconnection.
- **Subscription management**: real-time message delivery via WebSocket.

Default relays: `wss://relay.damus.io`, `wss://nos.lol`, `wss://relay.nostr.band`.

### Event Kind

Email messages use Nostr event kind `1050` (application-specific, range
10000-19999). The event content is the encrypted email body. Tags include
the recipient's public key (`["p", "<pubkey>"]`).

---

## Current Status

### What works

- Desktop email client (SvelteKit + Tauri)
- Self-hosted server (Python / FastAPI)
- IMAP/SMTP support for traditional email
- Multiple accounts
- Unified inbox
- Advanced search
- Nostr transport adapter
- Nostr identity generation (NIP-01/NIP-19)
- NIP-04 and NIP-44 encryption
- Multi-relay failover
- Encrypted message send/receive via Nostr relays
- Offline message delivery (relays as store-and-forward)

### What's missing

- Formal protocol specification
- Threat model and security audit
- Key rotation for Nostr identities
- Delivery confirmation
- Message expiration policies
- Relay selection optimization
- Metadata padding

---

## Security Status

The cryptographic primitives (Ed25519, X25519, AES-256-CBC, ChaCha20-Poly1305)
are well-known and widely vetted. However:

- The composition and wire format are **alpha-grade**.
- No third-party security audit has been performed.
- Metadata (sender, recipient, subject, size) is visible to relays.
- Relay operators can see who communicates with whom (but not the content).
- Forward secrecy is not yet implemented.
- The Nostr relay network relies on voluntary operation -- relays may go
  offline or censor content.

Treat this as a **research-grade reference implementation**.

---

## Repository Structure

```text
├── client/           Desktop client (SvelteKit + Tauri)
├── node/             Server (Python / FastAPI)
│   ├── src/
│   │   ├── nostr/           Nostr transport implementation
│   │   ├── mail_abstraction/  MailAdapter interface
│   │   ├── modules/openmail/  IMAP/SMTP email module
│   │   ├── internal/         Account management, storage
│   │   ├── routers/          HTTP API endpoints
│   │   └── helpers/          Logging, port scanning
│   └── tests/
│       ├── nostr/           Nostr-specific tests
│       ├── mail_abstraction/  Adapter tests
│       └── ...               Other tests
├── docs/             Documentation
├── scripts/          Dev/install scripts
└── .github/          CI workflows
```

---

## Development

### Prerequisites

- Python 3.13+ and [uv](https://github.com/astral-sh/uv)
- [Bun](https://bun.sh) and [Rust toolchain](https://tauri.app/start/prerequisites/)

### Install

Linux / macOS:

```sh
./install.sh
```

Windows:

```pwsh
pwsh -File scripts/install.ps1
```

### Run

Node server:

```sh
cd node
uv run python -m src.main
```

Desktop client:

```sh
cd client
bun run tauri dev
```

### Tests

```sh
cd node && uv run pytest
```

---

## Contributing

Contributions are welcome, particularly around:

- Nostr protocol integration
- Encryption and key management
- Relay behavior and selection
- Email standards (IMAP/SMTP)
- Client development
- Security review

---

## Origin

This project is derived from
[Openmail](https://github.com/burakorkmez/openmail), an open-source
self-hosted email client/server. Narada extends that foundation with
decentralized Nostr transport.

See [`LICENSE`](LICENSE) for details (Apache License 2.0).

---

<p align="center">
  <strong>Narada</strong><br>
  Decentralized email with Nostr transport.
</p>
