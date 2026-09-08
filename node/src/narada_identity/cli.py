"""Command-line interface for the Narada identity layer.

Usage::

    python -m src.narada_identity.cli generate <account_id>
    python -m src.narada_identity.cli show <account_id>
    python -m src.narada_identity.cli recover <account_id> "<word1 word2 ...>"
    python -m src.narada_identity.cli rotate <account_id>
    python -m src.narada_identity.cli rotate-x25519 <account_id>
    python -m src.narada_identity.cli key-update <account_id> <recipient_public_id>

The keystore backend is selected by :func:`src.narada_identity.keystore.default_keystore`.
Pass ``--memory`` to use the :class:`InMemoryKeystore` (no persistence).
Pass ``--passphrase <pw>`` to force the :class:`PassphraseKeystore`.
"""

from __future__ import annotations

import argparse
import sys

from .errors import NaradaIdentityError
from .identity import (
    generate_identity,
    identity_from_keystore,
    identity_from_mnemonic,
    rotate_identity,
    rotate_identity_preserve_x25519,
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
    except NaradaIdentityError as exc:
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


def cmd_rotate_x25519(args: argparse.Namespace) -> int:
    """Rotate the Ed25519 signing key while preserving the X25519 encryption key.

    This is the recommended rotation method (Option A): the new
    identity has a different Ed25519 key (and therefore a different
    narada1... public id) but the same X25519 encryption key, so
    existing peers can still decrypt messages addressed to the prior
    identity without an out-of-band re-keying exchange.
    """
    keystore = _build_keystore(args)
    if not keystore.has(args.account_id):
        print(
            f"error: no identity stored for {args.account_id!r}; nothing to rotate",
            file=sys.stderr,
        )
        return 1
    identity, mnemonic = rotate_identity_preserve_x25519(args.account_id, keystore)
    print(f"Account:    {identity.account_id}")
    print(f"Public id:  {identity.public_id}")
    print(f"X25519 key: preserved from prior identity")
    print()
    print("New recovery mnemonic (write this down; the old one is now invalid):")
    print(f"  {mnemonic}")
    print()
    print(
        "Next step: send a key-update envelope to each peer so they learn\n"
        "the new public id. Use `key-update <account_id> <recipient_pub_id>`."
    )
    return 0


def cmd_key_update(args: argparse.Namespace) -> int:
    """Build and print a key-update envelope for a recipient.

    The envelope is printed as JSON to stdout so the caller can
    ship it via the Narada transport layer.
    """
    import json

    keystore = _build_keystore(args)
    try:
        identity = identity_from_keystore(args.account_id, keystore)
    except NaradaIdentityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # The new identity should be the one currently stored (after
    # rotate-x25519 was called).  We need the *prior* identity to
    # sign the update.  For the CLI path, the caller must supply
    # the prior identity's seed or mnemonic.  As a simpler
    # approach, we accept the --new-public-id flag and build the
    # envelope from the current keystore state.
    #
    # However, the CLI cannot easily access the *old* key after
    # rotation (it was overwritten).  The practical path is:
    # the caller runs `rotate-x25519` which stores the new key,
    # then uses `key-update` with the stored (new) identity and
    # the *recipient* they want to notify.
    #
    # For this to work with the current keystore model, the
    # caller must supply the old public id and old seed via
    # --old-mnemonic.  If not supplied, we skip the envelope
    # and print instructions.
    if args.old_mnemonic:
        from .identity import identity_from_mnemonic

        old_identity = identity_from_mnemonic(
            args.account_id, args.old_mnemonic, keystore=None
        )
    else:
        print(
            "error: --old-mnemonic is required to build the key-update envelope.\n"
            "After rotate-x25519, the old key is no longer in the keystore.\n"
            "Supply the old mnemonic with --old-mnemonic <phrase>.",
            file=sys.stderr,
        )
        return 1

    from src.narada.key_update import make_key_update_envelope

    envelope = make_key_update_envelope(
        sender_identity=old_identity,
        recipient_public_id=args.recipient_public_id,
        new_identity=identity,
        not_after=args.not_after,
    )
    json.dump(envelope.as_dict(), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="Narada-identity",
        description="Manage Narada cryptographic identities for the Narada node.",
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

    p_rot_x = sub.add_parser(
        "rotate-x25519",
        help="Rotate Ed25519 key while preserving the X25519 encryption key (Option A).",
    )
    p_rot_x.add_argument("account_id")
    p_rot_x.set_defaults(func=cmd_rotate_x25519)

    p_ku = sub.add_parser(
        "key-update",
        help="Build a key-update envelope (v=3) for a recipient.",
    )
    p_ku.add_argument("account_id")
    p_ku.add_argument("recipient_public_id")
    p_ku.add_argument(
        "--old-mnemonic",
        default="",
        help="The OLD mnemonic (required; the old key was overwritten by rotate-x25519).",
    )
    p_ku.add_argument(
        "--not-after",
        type=int,
        default=None,
        help="Overlap window end (unix seconds). Default: 7 days from now.",
    )
    p_ku.set_defaults(func=cmd_key_update)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except NaradaIdentityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
