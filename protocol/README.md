# Lattice Protocol

This directory defines the Lattice protocol. Anything that travels over the
Lattice network — node-to-node messages, identity documents, handshakes,
delivery acknowledgements — is described here.

The protocol is the project. The clients and nodes are just reference
implementations.

## Status

Stub. The exact wire format, cryptography, and transport are not yet
specified. These documents are starting points for discussion; nothing here
should be treated as final.

## Layout

```
protocol/
├── spec.md            # Top-level protocol specification (overview)
├── identity.md        # Cryptographic identity format
├── message-format.md  # Encrypted message envelope
└── README.md
```

## Roadmap (from the project README)

- **Phase 1 — Cryptographic Identity.** Keypair generation, secure key
  storage, identity format, key rotation, key recovery.
- **Phase 2 — Lattice Protocol.** Protocol spec, message format, node
  identity, secure handshake, encrypted transport, message authentication,
  delivery acknowledgements, replay protection.
- **Phase 3 — Distributed Network.** Peer discovery, peer-to-peer
  communication, distributed routing, mailbox discovery, message
  synchronization, duplicate detection, node failure handling.
- **Phase 4 — Distributed Delivery.** Relay nodes, encrypted temporary
  storage, offline delivery, message expiration, relay selection, delivery
  confirmation, storage policies.
- **Phase 5 — Interoperability.** SMTP / IMAP gateways, Lattice -> SMTP,
  SMTP -> Lattice, identity mapping, spam prevention.
- **Phase 6 — Protocol Stabilization.** Formal spec, threat model, security
  audit, reference implementation, versioned protocol, compatibility
  guarantees.
