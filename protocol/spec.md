# Narada Protocol Specification (Stub)

> Status: **draft / discussion only.** Nothing in this document is final.
> See `identity.md` and `message-format.md` for sub-topics.

## Goals

- **Decentralization.** No single organization is required to operate the
  network. Anyone can run a node.
- **User ownership.** Users control their identity, keys, mailbox, node, and
  data.
- **Privacy.** Messages are encrypted to the recipient before they touch
  infrastructure that does not need plaintext access.
- **Minimal trust.** Nodes are assumed to fail, disappear, misbehave, or be
  compromised. The protocol should degrade gracefully.
- **Resilience.** Individual nodes going offline must not take the network
  down. Offline users should not mean undeliverable messages.
- **Interoperability.** Coexist with existing email (IMAP/SMTP) rather than
  requiring a hard migration.

## Non-goals (initial)

- Production-grade security. Narada is explicitly **not** considered secure
  yet; do not use it for sensitive communication.
- Compelling-with-existing-email compatibility beyond what the gateway
  (Phase 5) provides.
- Replacing the surface area of modern mail providers (search, calendar,
  contacts, etc.). The Narada protocol carries messages; clients may add
  features on top.

## Layers (proposed)

1. **Identity layer.** Public-key identities, key metadata, mailbox
   references. See `identity.md`.
2. **Transport layer.** Encrypted, authenticated, replay-protected transport
   between nodes. Underlying transport is TBD (probably a mix of TCP, QUIC,
   and onion-style relays).
3. **Message layer.** Encrypted message envelope, addressing, fragment
   reassembly. See `message-format.md`.
4. **Delivery layer.** Routing, mailbox discovery, store-and-forward relays
   for offline recipients.
5. **Gateway layer.** Bridges to conventional IMAP/SMTP. Lives in
   `gateway/`, not in this directory.

## Open questions

- Transport: TCP+TLS, QUIC, libp2p, or something custom?
- Discovery: well-known bootstrap nodes, DHT, signed peer lists, all of the
  above?
- Identity: pure Ed25519 public keys, or did:key-style self-describing
  identifiers?
- Metadata protection: how much do we try to hide, and at what cost?
- Spam / Sybil resistance: web-of-trust, proof-of-work, reputation, or
  accepted as out of scope initially?
