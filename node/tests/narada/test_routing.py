"""Tests for distributed routing (Phase 3 commit 4)."""

from __future__ import annotations

import pytest

from src.narada.directory import InMemoryDirectory
from src.narada.routing import (
    CachingDirectory,
    DistributedDirectory,
    PeerLookupError,
)
from src.narada.p2p.peer_lookup import (
    DirectoryEntry,
    InMemoryPeerLookupClient,
    NoopPeerLookupClient,
)


def test_caching_directory_passes_through_to_inner():
    inner = InMemoryDirectory()
    inner.add("narada1bob", "mem://bob", "bob@example.com")
    cache = CachingDirectory(inner)
    assert cache.lookup("narada1bob") == "mem://bob"
    assert cache.lookup("narada1missing") is None


def test_caching_directory_serves_from_cache_after_inner_emptied():
    inner = InMemoryDirectory()
    inner.add("narada1bob", "mem://bob", "bob@example.com")
    cache = CachingDirectory(inner)
    assert cache.lookup("narada1bob") == "mem://bob"
    inner.remove("narada1bob")
    # Cache still has the entry; the cache is the source of truth
    # until TTL expires or invalidate() is called.
    assert cache.lookup("narada1bob") == "mem://bob"
    cache.invalidate("narada1bob")
    assert cache.lookup("narada1bob") is None


def test_caching_directory_add_populates_cache():
    inner = InMemoryDirectory()
    cache = CachingDirectory(inner)
    cache.add("narada1x", "mem://x", "x@example.com")
    # Even with the inner directory emptied, cache returns the value.
    inner.remove("narada1x")
    assert cache.lookup("narada1x") == "mem://x"


def test_caching_directory_invalidate_all():
    inner = InMemoryDirectory()
    cache = CachingDirectory(inner)
def test_caching_directory_invalidate_all_forces_refresh():
    inner = InMemoryDirectory()
    cache = CachingDirectory(inner)
    cache.add("narada1x", "mem://x", "x@example.com")
    cache.invalidate()
    # Cache is cleared, but inner still has the value.
    assert cache.lookup("narada1x") == "mem://x"


def test_distributed_directory_peer_url_uses_mem_scheme():
    """Peer answers return a mem:// base_url the directory can store."""
    inner = InMemoryDirectory()
    peer = InMemoryPeerLookupClient()
    peer.publish(
        node_id="node1xyz",
        entry=DirectoryEntry(
            public_id="narada1bob",
            base_url="mem://host1:4440",
            account_id="bob@example.com",
        ),
    )
    dd = DistributedDirectory(inner, peer_client=peer)
    assert dd.lookup("narada1bob") == "mem://host1:4440"


def test_distributed_directory_ignores_mismatched_peer_answer():
    inner = InMemoryDirectory()
    peer = InMemoryPeerLookupClient()
    # Peer returns a record for a *different* public id than asked.
    peer.publish(
        node_id="node1xyz",
        entry=DirectoryEntry(
            public_id="narada1alice",
            base_url="host1:4440",
            account_id="alice@example.com",
        ),
    )
    dd = DistributedDirectory(inner, peer_client=peer)
    assert dd.lookup("narada1bob") is None
    assert inner.lookup("narada1bob") is None


def test_distributed_directory_hint_path():
    """A V2 recipient with a node-id hint is resolved via that node first."""
    from src.narada_identity.encoding import (
        IdentityVersion,
        decode_node_hint,
        encode_public_id,
    )

    ed = b"\x11" * 32
    x = b"\x22" * 32
    bob_v2 = encode_public_id(
        ed, x, version=IdentityVersion.V2, node_id_hint="node1hinted"
    )
    assert decode_node_hint(bob_v2) == "node1hinted"

    inner = InMemoryDirectory()
    peer = InMemoryPeerLookupClient()
    peer.publish(
        node_id="node1hinted",
        entry=DirectoryEntry(
            public_id=bob_v2,
            base_url="host-hinted:4440",
            account_id="bob@example.com",
        ),
    )
    dd = DistributedDirectory(inner, peer_client=peer)
    assert dd.lookup(bob_v2) == "host-hinted:4440"


def test_distributed_directory_hint_path_falls_back_to_broadcast():
    from src.narada_identity.encoding import (
        IdentityVersion,
        encode_public_id,
    )

    ed = b"\x33" * 32
    x = b"\x44" * 32
    bob_v2 = encode_public_id(
        ed, x, version=IdentityVersion.V2, node_id_hint="node1absent"
    )

    inner = InMemoryDirectory()
    peer = InMemoryPeerLookupClient()
    # Different node publishes the answer.
    peer.publish(
        node_id="node1other",
        entry=DirectoryEntry(
            public_id=bob_v2,
            base_url="host-other:4440",
            account_id="bob@example.com",
        ),
    )
    dd = DistributedDirectory(inner, peer_client=peer)
    assert dd.lookup(bob_v2) == "host-other:4440"


def test_distributed_directory_handles_peer_lookup_error():
    class BrokenClient:
        def ask_node(self, node_id, public_id):
            raise PeerLookupError("nope")

        def ask_all(self, public_id):
            return []

    inner = InMemoryDirectory()
    dd = DistributedDirectory(inner, peer_client=BrokenClient())
    assert dd.lookup("narada1bob") is None
