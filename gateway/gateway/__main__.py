"""Narada Gateway entry point (Phase 5).

Commands:
    check       — Validate the mapping and exit.
    daemon      — Start the long-running gateway daemon.
    ingest      — Bulk-import messages from IMAP into Narada.
    serve-imap  — Start a read-only IMAP server for the Narada mailbox.
    status      — Query a running daemon's status.
    poll        — Trigger a single poll on a running daemon.
    reload      — Reload the mapping on a running daemon.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .mapping import IdentityMapping
from .orchestrator import Gateway
from .sender import SmtpSender


def cmd_check(args: argparse.Namespace) -> int:
    mapping = IdentityMapping.from_file(args.mapping)
    summary = {
        "narada_ids": sorted(mapping.narada_ids()),
        "smtp_addresses": sorted(mapping.smtp_addresses()),
    }
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_daemon(args: argparse.Namespace) -> int:
    from .daemon import GatewayDaemon

    daemon = GatewayDaemon(
        mapping_path=args.mapping,
        data_dir=Path(args.data_dir) if args.data_dir else None,
        smtp_host=args.smtp_host,
        smtp_port=args.smtp_port,
        smtp_user=args.smtp_user,
        smtp_password=args.smtp_password,
        smtp_from=args.smtp_from,
        imap_host=args.imap_host,
        imap_port=args.imap_port,
        imap_user=args.imap_user,
        imap_password=args.imap_password,
        imap_folder=args.imap_folder,
        poll_interval=args.poll_interval,
        imap_server_port=args.imap_server_port,
        control_port=args.control_port,
    )
    daemon.run()
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    from .ingester import ImapIngester

    mapping = IdentityMapping.from_file(args.mapping)
    ingester = ImapIngester(
        mapping=mapping,
        data_dir=Path(args.data_dir) if args.data_dir else Path.home() / ".openmail",
        imap_host=args.imap_host,
        imap_port=args.imap_port,
        username=args.imap_user,
        password=args.imap_password,
        folder=args.imap_folder,
    )
    result = ingester.ingest(limit=args.limit)
    print(
        json.dumps(
            {
                "imported": result.imported,
                "skipped": result.skipped,
                "errors": result.errors,
            },
            indent=2,
        )
    )
    return 0


def cmd_serve_imap(args: argparse.Namespace) -> int:
    from .imap_server import NaradaImapServer

    server = NaradaImapServer(
        data_dir=Path(args.data_dir) if args.data_dir else Path.home() / ".openmail",
        account_id=args.account,
        host="127.0.0.1",
        port=args.port,
    )
    print(f"Starting Narada IMAP server on 127.0.0.1:{args.port}...")
    server.start_background()
    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
        print("IMAP server stopped.")
    return 0


def _control_request(
    control_port: int, method: str, path: str
) -> dict | None:
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    try:
        sock.connect(("127.0.0.1", control_port))
        request = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
        sock.sendall(request.encode())
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        # Parse body after the blank line.
        body_start = data.find(b"\r\n\r\n")
        if body_start == -1:
            return None
        body = data[body_start + 4 :]
        return json.loads(body.decode("utf-8"))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return None
    finally:
        sock.close()


def cmd_status(args: argparse.Namespace) -> int:
    result = _control_request(args.control_port, "GET", "/status")
    if result is None:
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_poll(args: argparse.Namespace) -> int:
    result = _control_request(args.control_port, "POST", "/poll")
    if result is None:
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_reload(args: argparse.Namespace) -> int:
    result = _control_request(args.control_port, "POST", "/reload")
    if result is None:
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if result.get("success") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="narada-gateway",
        description="Narada <-> SMTP/IMAP gateway (Phase 5)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # check
    p_check = sub.add_parser("check", help="Validate the mapping and exit.")
    p_check.add_argument("--mapping", type=Path, required=True)
    p_check.set_defaults(func=cmd_check)

    # daemon
    p_daemon = sub.add_parser("daemon", help="Start the long-running gateway daemon.")
    p_daemon.add_argument("--mapping", type=Path, required=True)
    p_daemon.add_argument("--data-dir", default="")
    p_daemon.add_argument("--smtp-host", default="")
    p_daemon.add_argument("--smtp-port", type=int, default=587)
    p_daemon.add_argument("--smtp-user", default="")
    p_daemon.add_argument("--smtp-password", default="")
    p_daemon.add_argument("--smtp-from", default="")
    p_daemon.add_argument("--imap-host", default="")
    p_daemon.add_argument("--imap-port", type=int, default=993)
    p_daemon.add_argument("--imap-user", default="")
    p_daemon.add_argument("--imap-password", default="")
    p_daemon.add_argument("--imap-folder", default="INBOX")
    p_daemon.add_argument(
        "--poll-interval", type=float, default=300.0,
        help="Seconds between inbound polls (default 300).",
    )
    p_daemon.add_argument(
        "--imap-server-port", type=int, default=None,
        help="Port for the Narada→IMAP server (default: disabled).",
    )
    p_daemon.add_argument(
        "--control-port", type=int, default=1144,
        help="Port for the control REST API (default 1144).",
    )
    p_daemon.set_defaults(func=cmd_daemon)

    # ingest
    p_ingest = sub.add_parser("ingest", help="Bulk-import from IMAP into Narada.")
    p_ingest.add_argument("--mapping", type=Path, required=True)
    p_ingest.add_argument("--data-dir", default="")
    p_ingest.add_argument("--imap-host", default="")
    p_ingest.add_argument("--imap-port", type=int, default=993)
    p_ingest.add_argument("--imap-user", default="")
    p_ingest.add_argument("--imap-password", default="")
    p_ingest.add_argument("--imap-folder", default="INBOX")
    p_ingest.add_argument(
        "--limit", type=int, default=None,
        help="Maximum messages to ingest.",
    )
    p_ingest.set_defaults(func=cmd_ingest)

    # serve-imap
    p_serve = sub.add_parser("serve-imap", help="Start a Narada→IMAP server.")
    p_serve.add_argument("--data-dir", default="")
    p_serve.add_argument("--account", default=None)
    p_serve.add_argument(
        "--port", type=int, default=1143,
        help="IMAP listen port (default 1143).",
    )
    p_serve.set_defaults(func=cmd_serve_imap)

    # status
    p_status = sub.add_parser("status", help="Query a running daemon's status.")
    p_status.add_argument(
        "--control-port", type=int, default=1144,
    )
    p_status.set_defaults(func=cmd_status)

    # poll
    p_poll = sub.add_parser("poll", help="Trigger a single poll on a running daemon.")
    p_poll.add_argument("--control-port", type=int, default=1144)
    p_poll.set_defaults(func=cmd_poll)

    # reload
    p_reload = sub.add_parser("reload", help="Reload the mapping on a running daemon.")
    p_reload.add_argument("--control-port", type=int, default=1144)
    p_reload.set_defaults(func=cmd_reload)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
