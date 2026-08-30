"""Command-line interface for the Lattice identity layer.

Usage:

    python -m src.lattice_identity.cli generate <account_id>
    python -m src.lattice_identity.cli show <account_id>
    python -m src.lattice_identity.cli recover <account_id> "<word1 word2 ...>"

The keystore backend is selected by :func:`src.lattice_identity.keystore.default_keystore`.
Pass ``--memory`` to use the :class:`InMemoryKeystore` (no persistence).
Pass ``--passphrase <pw>`` to force the :class:`PassphraseKeystore`.
"""

from __future__ import annotations

import argparse
import sys

from .errors import LatticeIdentityError
from .identity import (
    generate_identity,
    identity_from_keystore,
    identity_from_mnemonic,
    rotate_identity,
)
from .keystore import InMemoryKeystore, default_keystore


def _build_keystore(args: argparse.Namespace):
    if args.memory:
        return InMemoryKeystore()
    return default_keystore(passphrase=args.passphrase)


def cmd_generate(args: argparse.Namespace) -> int:
    keystore = _build_keystore(args)
    identity, mnemonic = generate_identity(args.account_id, keystore=keystore)
    print(f"Account:    {identity.account_id}")
    print(f"Public id:  {identity.public_id}")
    print()
    print("Recovery mnemonic (write this down; it is the only backup):")
    print(f"  {mnemonic}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    keystore = _build_keystore(args)
    try:
        identity = identity_from_keystore(args.account_id, keystore)
    except LatticeIdentityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Account:    {identity.account_id}")
    print(f"Public id:  {identity.public_id}")
    return 0


def cmd_recover(args: argparse.Namespace) -> int:
    keystore = _build_keystore(args)
    identity = identity_from_mnemonic(args.account_id, args.mnemonic, keystore=keystore)
    print(f"Account:    {identity.account_id}")
    print(f"Public id:  {identity.public_id}")
    print("Identity recovered and stored.")
    return 0


def cmd_rotate(args: argparse.Namespace) -> int:
    keystore = _build_keystore(args)
    if not keystore.has(args.account_id):
        print(
            f"error: no identity stored for {args.account_id!r}; nothing to rotate",
            file=sys.stderr,
        )
        return 1
    identity, mnemonic = rotate_identity(args.account_id, keystore)
    print(f"Account:    {identity.account_id}")
    print(f"Public id:  {identity.public_id}")
    print()
    print("New recovery mnemonic (write this down; the old one is now invalid):")
    print(f"  {mnemonic}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lattice-identity",
        description="Manage Lattice cryptographic identities for the Lattice node.",
    )
    parser.add_argument("--memory", action="store_true", help="Use in-memory keystore (no persistence).")
    parser.add_argument("--passphrase", help="Passphrase for the filesystem-backed keystore.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser("generate", help="Generate a new identity and store it.")
    p_gen.add_argument("account_id")
    p_gen.set_defaults(func=cmd_generate)

    p_show = sub.add_parser("show", help="Show the public id of a stored identity.")
    p_show.add_argument("account_id")
    p_show.set_defaults(func=cmd_show)

    p_rec = sub.add_parser("recover", help="Recover an identity from a 12-word mnemonic.")
    p_rec.add_argument("account_id")
    p_rec.add_argument("mnemonic")
    p_rec.set_defaults(func=cmd_recover)

    p_rot = sub.add_parser("rotate", help="Replace the stored seed with a new one.")
    p_rot.add_argument("account_id")
    p_rot.set_defaults(func=cmd_rotate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except LatticeIdentityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
