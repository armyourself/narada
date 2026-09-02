"""Per-node Narada identity (Phase 3 wiring).

A Narada **node** (the daemon, not a user) has its own Ed25519 keypair
that is independent of any per-account identity. The node identity is
used to:

* sign the optional ``sender_node_id`` / ``sender_node_signature`` fields
  on outgoing envelopes (so recipients can attribute an envelope to a
  specific daemon);
* sign delivery acknowledgements (R3b).

The node identity is **not** used to encrypt payloads. End-to-end
encryption between sender and recipient continues to use the per-account
X25519 keys carried in their ``narada1...`` user identities.

Two privacy modes are supported:

* **default (``ephemeral=False``)** — the node keypair is generated
  fresh on first use and persisted to disk at
  ``<data_dir>/node_identity/seed``. All envelopes leaving this node
  carry the same ``node1...`` public id until the file is deleted or
  rotated. This is a **linkability vector**: an observer who can read
  the network can correlate envelopes by node.

* **``ephemeral=True``** — a fresh Ed25519 keypair is generated for
  every envelope. There is **no on-disk state**, so the node is
  unlinkable across envelopes at the cost of an extra signature and a
  small amount of garbage collection.

Default is the persistent mode because it makes delivery acks and
future relay-selection work straightforward; users who need "max
privacy" can pass ``ephemeral=True`` to :func:`load_or_create`.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

from src.narada_identity.encoding import encode_node_id, decode_node_id
from src.narada_identity.errors import NaradaIdentityError


_NODE_SEED_LEN = 32  # Ed25519 private keys are 32 bytes (the seed).


class NodeIdentityError(NaradaIdentityError):
    """Raised on any failure loading or using a node identity."""


@dataclass(frozen=True)
class NaradaNodeIdentity:
    """A node-level Narada identity: Ed25519 only."""

    public_id: str  # bech32m "node1..."
    ed25519_public_bytes: bytes
    _private_key: Ed25519PrivateKey

    @classmethod
    def generate(cls) -> "NaradaNodeIdentity":
        """Generate a fresh random node identity (in-memory only)."""
        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key()
        pub_bytes = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
        return cls(
            public_id=encode_node_id(pub_bytes),
            ed25519_public_bytes=pub_bytes,
            _private_key=priv,
        )

    def sign(self, data: bytes) -> bytes:
        """Return a raw 64-byte Ed25519 signature over ``data``."""
        return self._private_key.sign(data)

    @classmethod
    def from_seed(cls, seed: bytes) -> "NaradaNodeIdentity":
        """Build a node identity from a 32-byte seed."""
        if len(seed) != _NODE_SEED_LEN:
            raise NodeIdentityError(
                f"node seed must be {_NODE_SEED_LEN} bytes, got {len(seed)}"
            )
        priv = Ed25519PrivateKey.from_private_bytes(seed)
        pub = priv.public_key()
        pub_bytes = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
        return cls(
            public_id=encode_node_id(pub_bytes),
            ed25519_public_bytes=pub_bytes,
            _private_key=priv,
        )


# --- Default persistence path --------------------------------------------


def _seed_path(data_dir: Path) -> Path:
    """Return the canonical on-disk path for the node seed."""
    return Path(str(data_dir)) / "node_identity" / "seed"


def _persist_seed(path: Path, seed: bytes) -> None:
    """Write ``seed`` to ``path`` with best-effort 0600 permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # We store the raw 32-byte seed rather than DER to keep the on-disk
    # format trivially auditable. The file is per-node and never leaves
    # the machine; if an attacker can read it, they can already read the
    # user's mailbox.
    path.write_bytes(seed)
    try:
        os.chmod(path, 0o600)
    except (OSError, NotImplementedError):
        # Windows / unusual FS — chmod may be a no-op; that's fine.
        pass


def load_or_create(
    data_dir: Path, *, ephemeral: bool = False
) -> NaradaNodeIdentity:
    """Load the persistent node identity or create one.

    Parameters
    ----------
    data_dir:
        Node data directory. The seed is persisted under
        ``<data_dir>/node_identity/seed``.
    ephemeral:
        If True, always return a freshly generated identity and skip the
        disk read/write. Use this for privacy-maximising callers.
    """
    if ephemeral:
        return NaradaNodeIdentity.generate()

    path = _seed_path(Path(str(data_dir)))
    if path.exists():
        try:
            seed = path.read_bytes()
        except OSError as exc:
            raise NodeIdentityError(
                f"could not read node identity at {path}: {exc}"
            ) from exc
        if len(seed) != _NODE_SEED_LEN:
            raise NodeIdentityError(
                f"node identity seed at {path} is {_NODE_SEED_LEN}-byte "
                f"expected, got {len(seed)} bytes"
            )
        return NaradaNodeIdentity.from_seed(seed)

    seed = secrets.token_bytes(_NODE_SEED_LEN)
    try:
        _persist_seed(path, seed)
    except OSError as exc:
        # If we cannot persist, fall back to in-memory only — better
        # than failing to start the node over a permissions issue.
        return NaradaNodeIdentity.from_seed(seed)
    return NaradaNodeIdentity.from_seed(seed)


def verify_node_signature(
    public_id: str, signature: bytes, data: bytes
) -> bool:
    """Verify a node signature against ``public_id``.

    Returns False on any error (malformed id, bad signature length,
    cryptographic mismatch). Never raises.
    """
    try:
        ed_pub_bytes = decode_node_id(public_id)
    except NaradaIdentityError:
        return False
    if len(signature) != 64:
        return False
    try:
        pub = Ed25519PublicKey.from_public_bytes(ed_pub_bytes)
        pub.verify(signature, data)
        return True
    except Exception:
        return False


__all__ = [
    "NaradaNodeIdentity",
    "NodeIdentityError",
    "load_or_create",
    "verify_node_signature",
]