# Lattice Identity

> Status: **specified.** The on-the-wire encoding, key types, and
> recovery format are defined here. Implementation lives in
> `node/src/lattice_identity/`.

## What an identity is

A Lattice identity binds together:

- A **public key** used to verify signatures and derive shared secrets.
- A **node identity**: one or more node references where the user can be
  reached (mailbox location, supported transport, etc.). *Not specified
  here; lands with the Lattice protocol (Phase 2+).*
- **Mailbox information**: how to deliver messages to this identity.
  *Not specified here.*
- **Key metadata**: algorithm, version, creation time, rotation history,
  expiry. The wire format carries only the version byte; richer
  metadata will live in a separate node document.

The private key never appears in the identity document. It stays with
the user.

## Public-id string format

A Lattice identity is encoded as a **bech32m** string (BIP-350) with the
human-readable prefix `lattice`:

```
lattice1<bech32m-checksummed-payload>
```

### Payload layout

```
Offset  Length  Field
------  ------  -----
0       1       version (currently 0x01)
1       32      Ed25519 public key (signing)
33      32      X25519 public key (encryption)
```

Total: **65 bytes** before bech32m encoding. The version byte allows
future migration (e.g. to post-quantum algorithms) without breaking
parsers.

### Why two keys

- **Ed25519** is used to sign messages and identity assertions. It is
  fast, has small signatures (~64 bytes), and is widely audited.
- **X25519** is used to derive a per-recipient shared secret via ECDH,
  which is then used (via HKDF + an AEAD) to encrypt message bodies.

The X25519 keypair is **deterministically derived from the Ed25519
seed** via HKDF-SHA256 with the info string
`b"lattice-x25519-from-ed25519-seed"`. A single 32-byte seed is
therefore enough to recover both halves. This keeps the recovery
mnemonic small (12 words) and removes the risk of the two keys
drifting apart.

## Recovery: 12-word BIP-39 mnemonic

A Lattice identity can be recovered from a 12-word BIP-39 mnemonic:

1. Decode the mnemonic to its 16-byte entropy (the BIP-39 checksum is
   verified by the standard wordlist).
2. Hash the entropy with SHA-256 to obtain a 32-byte seed.
3. Derive the Ed25519 keypair from the 32-byte seed; the X25519
   keypair follows from HKDF as above.

The mnemonic is the only durable backup of the private material if no
keystore is configured.

## Keystore backends

The private seed is stored by a `LatticeKeystore` chosen at runtime:

- **`InMemoryKeystore`** — process-local; used for tests and the
  `--no-persist` CLI mode. Not durable.
- **`KeyringKeystore`** — production default. Stores the seed in the
  operating system's keyring (SecretService on Linux, Credential
  Manager on Windows, Keychain on macOS) under a service name derived
  from `account_id`. No passphrase prompt is required; the OS protects
  access.
- **`PassphraseKeystore`** — fallback for headless servers with no OS
  keyring. The seed is encrypted with a passphrase via PBKDF2-HMAC-SHA256
  (200 000 iterations) + AES-GCM and stored as a file under
  `~/.lattice/keystore/<account_id>.bin` (mode 0600).

The same interface is exposed via the FastAPI router
`/lattice/identity/...` and the CLI
`python -m src.lattice_identity.cli ...`.

## Signing and ECDH

Given a `LatticeIdentity` and another party's public id:

- `identity.sign(data)` returns an Ed25519 signature.
- `identity.shared_secret_with(peer_public_id)` decodes the peer's
  `lattice1...` id, extracts the X25519 public key, and returns the 32-byte
  ECDH output. **Callers should run this through HKDF before using it
  as a symmetric key.** The raw ECDH output is exposed for testability.

## Required properties (initial)

- **Self-authenticating.** Given an identity, a verifier can recover
  both public keys from the bech32m string alone (no external
  authority).
- **Self-contained.** Reading an identity requires no state beyond the
  string.
- **Rotatable.** A user can publish a new identity that supersedes an
  old one without losing the chain of trust. The rotation mechanism
  lives in the protocol layer (Phase 2+); today, rotation produces a
  fresh `lattice1...` with no on-the-wire link to its predecessor.
- **Recoverable.** A user can recover the identity from the 12-word
  mnemonic if the keystore is wiped.

## Open questions

- Long-form vs short-form identifiers (think email address vs
  fingerprint). `lattice1...` is the long form; short forms may be
  introduced later.
- How key rotation and recovery interact on the wire.
- How to represent a user with multiple devices (sub-identities,
  device signing keys, etc.).
- Metadata envelope: signing-key creation time, expiry, supported
  algorithms. Will live in a separate document; not carried in the
  bech32m string.
