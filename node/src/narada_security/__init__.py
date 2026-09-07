"""Security helpers for the Narada node.

This package collects small, focused helpers that harden the on-disk
and wire-protocol surfaces against the threats catalogued in

* ``docs/security/threat-model.md``

The helpers are intentionally small and orthogonal: each addresses
one threat. They are wired into the existing modules rather than
introducing a parallel infrastructure.
"""
