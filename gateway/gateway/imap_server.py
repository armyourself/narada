"""Lightweight IMAP server that exposes a Narada mailbox (Phase 5).

:class:`NaradaImapServer` presents a virtual IMAP mailbox backed by
the Narada JSONL mailbox store (``<data_dir>/etc/mailbox.<account>.jsonl``).
A legacy email client can connect via IMAP, authenticate, LIST
folders, SELECT INBOX, FETCH messages, and SEARCH.

The server speaks a minimal IMAP4rev1 dialect: enough for a
standard mail client to read Narada messages.  Write operations
(APPEND, STORE, EXPUNGE) are intentionally out of scope — this
is a *read-only* view of the Narada inbox.

Wire protocol
-------------

The server speaks text over a plain TCP socket (no TLS in Phase 5;
the server is intended for localhost / loopback use).  Each client
session is handled in a single thread via blocking I/O.

Usage::

    server = NaradaImapServer(data_dir=Path("~/.openmail"), port=1143)
    server.start_background()  # daemon thread
    ...
    server.shutdown()
"""

from __future__ import annotations

import json
import logging
import re
import select
import socket
import struct
import threading
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

log = logging.getLogger("narada.imap_server")

_IMAP_GREETING = b"* OK Narada IMAP server ready\r\n"
_CAPABILITIES = b"* CAPABILITY IMAP4rev1 IDLE NAMESPACE AUTH=PLAIN\r\n"
_BYE = b"* BYE Server shutting down\r\n"
_OK_TAGGED = b"%s OK"
_NO_TAGGED = b"%s NO"
_BAD_TAGGED = b"%s BAD"


class NaradaImapServer:
    """Read-only IMAP server backed by a Narada mailbox JSONL file.

    Parameters
    ----------
    data_dir:
        The Narada node data directory (contains ``etc/mailbox.*.jsonl``).
    account_id:
        The account whose mailbox to serve.  If *None*, the server
        serves the first mailbox file it finds.
    host:
        Bind address (default ``127.0.0.1``).
    port:
        Bind port (default ``1143``).
    """

    def __init__(
        self,
        *,
        data_dir: Path,
        account_id: Optional[str] = None,
        host: str = "127.0.0.1",
        port: int = 1143,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._account_id = account_id
        self._host = host
        self._port = port
        self._server_socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # --- Lifecycle --------------------------------------------------------

    def start_background(self) -> None:
        """Start the IMAP server in a daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._serve, daemon=True, name="narada-imap"
        )
        self._thread.start()

    def shutdown(self) -> None:
        """Stop the server and join the background thread."""
        self._running = False
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=5)

    @property
    def is_running(self) -> bool:
        return self._running

    # --- Mailbox loading --------------------------------------------------

    def _mailbox_path(self, account_id: str) -> Optional[Path]:
        safe = _safe_account_id(account_id)
        path = self._data_dir / "etc" / f"mailbox.{safe}.jsonl"
        return path if path.exists() else None

    def _load_messages(self, account_id: str) -> list[dict]:
        path = self._mailbox_path(account_id)
        if path is None:
            return []
        messages: list[dict] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    messages.append(rec)
                except json.JSONDecodeError:
                    continue
        except OSError:
            return []
        return messages

    def _resolve_account(self) -> str:
        if self._account_id is not None:
            return self._account_id
        mailbox_dir = self._data_dir / "etc"
        if not mailbox_dir.exists():
            return "unknown"
        for p in sorted(mailbox_dir.glob("mailbox.*.jsonl")):
            name = p.stem.removeprefix("mailbox.").removesuffix(".jsonl")
            if name and name != "unknown":
                return name
        return "unknown"

    # --- Server loop ------------------------------------------------------

    def _serve(self) -> None:
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.settimeout(1.0)
        try:
            self._server_socket.bind((self._host, self._port))
            self._server_socket.listen(5)
            log.info("IMAP server listening on %s:%d", self._host, self._port)
            while self._running:
                try:
                    client_sock, addr = self._server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                t = threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, addr),
                    daemon=True,
                )
                t.start()
        except Exception as exc:
            log.error("IMAP server error: %s", exc)
        finally:
            self._running = False

    def _handle_client(
        self, sock: socket.socket, addr: tuple[str, int]
    ) -> None:
        log.info("IMAP client connected: %s", addr)
        try:
            sock.sendall(_IMAP_GREETING)
            authenticated = False
            account_id = self._resolve_account()
            selected_folder: Optional[str] = None
            messages: list[dict] = []
            tag_counter = 0
            buf = b""
            while self._running:
                try:
                    data = sock.recv(4096)
                except (ConnectionResetError, OSError):
                    break
                if not data:
                    break
                buf += data
                while b"\r\n" in buf:
                    line, buf = buf.split(b"\r\n", 1)
                    line_str = line.decode("utf-8", errors="replace")
                    tag_counter += 1
                    response = self._process_line(
                        line_str,
                        authenticated=authenticated,
                        account_id=account_id,
                        selected_folder=selected_folder,
                        messages=messages,
                    )
                    if response is None:
                        continue
                    action, text = response
                    if action == "auth_ok":
                        authenticated = True
                        sock.sendall(b"%s OK LOGIN completed\r\n" % b"A" + str(tag_counter).encode())
                    elif action == "auth_fail":
                        sock.sendall(b"%s NO Authentication failed\r\n" % b"A" + str(tag_counter).encode())
                    elif action == "select":
                        selected_folder = text
                        messages = self._load_messages(account_id)
                        exists_line = f"* {len(messages)} EXISTS\r\n".encode()
                        recent_line = b"* 0 RECENT\r\n"
                        flags_line = b"* FLAGS (\\Seen \\Answered \\Flagged \\Deleted \\Draft)\r\n"
                        ok_line = (
                            b"%s OK [READ-ONLY] SELECT completed\r\n"
                            % (b"A" + str(tag_counter).encode())
                        )
                        sock.sendall(exists_line + recent_line + flags_line + ok_line)
                    elif action == "list":
                        sock.sendall(text + b"\r\n")
                        sock.sendall(
                            b"A%d OK LIST completed\r\n" % tag_counter
                        )
                    elif action == "fetch":
                        for chunk in text:
                            sock.sendall(chunk + b"\r\n")
                        sock.sendall(
                            b"A%d OK FETCH completed\r\n" % tag_counter
                        )
                    elif action == "search":
                        sock.sendall(text + b"\r\n")
                        sock.sendall(
                            b"A%d OK SEARCH completed\r\n" % tag_counter
                        )
                    elif action == "capability":
                        sock.sendall(_CAPABILITIES)
                        sock.sendall(
                            b"A%d OK CAPABILITY completed\r\n" % tag_counter
                        )
                    elif action == "noop":
                        sock.sendall(
                            b"A%d OK NOOP completed\r\n" % tag_counter
                        )
                    elif action == "logout":
                        sock.sendall(_BYE)
                        sock.sendall(
                            b"A%d OK LOGOUT completed\r\n" % tag_counter
                        )
                        return
                    elif action == "ok":
                        sock.sendall(
                            b"A%d OK %s\r\n" % (tag_counter, text.encode())
                        )
                    elif action == "no":
                        sock.sendall(
                            b"A%d NO %s\r\n" % (tag_counter, text.encode())
                        )
                    elif action == "bad":
                        sock.sendall(
                            b"A%d BAD %s\r\n" % (tag_counter, text.encode())
                        )
        except Exception as exc:
            log.error("IMAP client handler error: %s", exc)
        finally:
            try:
                sock.close()
            except Exception:
                pass
            log.info("IMAP client disconnected: %s", addr)

    # --- Command processing -----------------------------------------------

    def _process_line(
        self,
        line: str,
        *,
        authenticated: bool,
        account_id: str,
        selected_folder: Optional[str],
        messages: list[dict],
    ) -> Optional[tuple[str, str | bytes | list[bytes]]]:
        """Parse one IMAP command line and return a response tuple.

        Returns ``(action, text)`` where action is one of:
        ``auth_ok``, ``auth_fail``, ``select``, ``list``, ``fetch``,
        ``search``, ``capability``, ``noop``, ``logout``, ``ok``,
        ``no``, ``bad``, or *None* for empty lines.
        """
        line = line.strip()
        if not line:
            return None

        # Tagged command: ``TAG COMMAND ...``
        m = re.match(r"^([A-Za-z0-9]+)\s+(.+)$", line)
        if m is None:
            return ("bad", "Invalid command")

        tag = m.group(1)
        cmd_part = m.group(2).strip()
        parts = cmd_part.split(None, 1)
        command = parts[0].upper()
        args = parts[1] if len(parts) > 1 else ""

        if command == "CAPABILITY":
            return ("capability", "")

        if command == "NOOP":
            return ("noop", "")

        if command == "LOGOUT":
            return ("logout", "")

        if command == "LOGIN":
            # Accept any login for Phase 5 (localhost only).
            return ("auth_ok", "")

        if not authenticated:
            return ("no", "Not authenticated")

        if command == "LIST":
            return self._cmd_list(args, account_id)
        if command == "SELECT" or command == "EXAMINE":
            folder = args.strip().strip('"')
            return ("select", folder)
        if command == "FETCH":
            return self._cmd_fetch(args, messages)
        if command == "SEARCH":
            return self._cmd_search(args, messages)
        if command == "STATUS":
            return self._cmd_status(args, account_id)
        if command == "NAMESPACE":
            return ("ok", 'NIL NIL NIL')
        if command == "ID":
            return self._cmd_id()
        if command in ("STORE", "COPY", "MOVE", "EXPUNGE", "APPEND", "SUBSCRIBE", "UNSUBSCRIBE"):
            return ("no", f"{command} not supported (read-only server)")

        return ("bad", f"Unknown command: {command}")

    def _cmd_list(
        self, args: str, account_id: str
    ) -> tuple[str, bytes]:
        # LIST "" "*" -> returns all folders.
        # LIST "" "INBOX" -> returns INBOX.
        ref = args.strip()
        # Simple: always return INBOX.
        folder_name = b'"INBOX"'
        list_resp = (
            b'* LIST (\\HasNoChildren) "/" ' + folder_name + b"\r\n"
        )
        return ("list", list_resp)

    def _cmd_fetch(
        self, args: str, messages: list[dict]
    ) -> tuple[str, list[bytes]]:
        # FETCH <sequence-set> <macro-or-items>
        # For Phase 5, support FETCH ALL and FETCH RFC822.
        seq_match = re.match(r"(\S+)\s+(.+)", args, re.IGNORECASE)
        if seq_match is None:
            return ("bad", "Invalid FETCH arguments")

        seq_set = seq_match.group(1)
        fetch_items = seq_match.group(2).strip().upper()

        indices = _parse_seq_set(seq_set, len(messages))
        responses: list[bytes] = []
        for idx in indices:
            if idx < 0 or idx >= len(messages):
                continue
            rec = messages[idx]
            rfc822 = _record_to_rfc822(rec)
            raw_bytes = rfc822.as_bytes()
            uid = idx + 1
            body = (
                b"* %d FETCH (RFC822 {%d}\r\n" % (uid, len(raw_bytes))
                + raw_bytes
                + b")\r\n"
            )
            responses.append(body)
        return ("fetch", responses)

    def _cmd_search(
        self, args: str, messages: list[dict]
    ) -> tuple[str, bytes]:
        # SEARCH ALL -> return all UIDs.
        # SEARCH UNSEEN -> return UIDs where \Seen not in flags.
        criterion = args.strip().upper()
        uids: list[int] = []
        for idx, rec in enumerate(messages):
            uid = idx + 1
            flags = [f.lower() for f in rec.get("flags", [])]
            if criterion == "ALL" or criterion == "":
                uids.append(uid)
            elif criterion == "UNSEEN":
                if "\\seen" not in flags:
                    uids.append(uid)
            elif criterion.startswith("SUBJECT"):
                # Simple subject search.
                search_val = _extract_search_value(criterion)
                subj = rec.get("subject", "").lower()
                if search_val in subj:
                    uids.append(uid)
            else:
                # Default: return all.
                uids.append(uid)
        uid_str = " ".join(str(u) for u in uids)
        return ("search", f"* SEARCH {uid_str}".encode())

    def _cmd_status(self, args: str, account_id: str) -> tuple[str, bytes]:
        # STATUS INBOX (MESSAGES UNSEEN) -> synthetic counts.
        messages = self._load_messages(account_id)
        total = len(messages)
        unseen = sum(
            1 for m in messages if "\\seen" not in [f.lower() for f in m.get("flags", [])]
        )
        return (
            "ok",
            f'* STATUS "INBOX" (MESSAGES {total} UNSEEN {unseen})'.encode(),
        )

    def _cmd_id(self) -> tuple[str, bytes]:
        return (
            "ok",
            b'* ID ("name" "Narada" "version" "0.1.0" "vendor" "Narada")',
        )


# --- Helpers --------------------------------------------------------------


def _safe_account_id(account_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._@+-" else "_" for c in account_id)
    return safe or "unknown"


def _parse_seq_set(seq_set: str, total: int) -> list[int]:
    """Parse an IMAP sequence set into 0-based indices.

    Supports: ``1``, ``1:3``, ``1,3,5``, ``*`` (last).
    """
    indices: list[int] = []
    for part in seq_set.split(","):
        part = part.strip()
        if ":" in part:
            lo, hi = part.split(":", 1)
            lo = lo.strip()
            hi = hi.strip()
            lo_int = int(lo) if lo != "*" else total
            hi_int = int(hi) if hi != "*" else total
            for i in range(lo_int, hi_int + 1):
                idx = i - 1  # 0-based
                if 0 <= idx < total:
                    indices.append(idx)
        else:
            val = int(part) if part != "*" else total
            idx = val - 1
            if 0 <= idx < total:
                indices.append(idx)
    return sorted(set(indices))


def _extract_search_value(criterion: str) -> str:
    """Extract the search value from e.g. 'SUBJECT \"hello\"'."""
    m = re.search(r'SUBJECT\s+"([^"]*)"', criterion, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    m = re.search(r"SUBJECT\s+(\S+)", criterion, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    return ""


def _record_to_rfc822(rec: dict) -> EmailMessage:
    """Convert a Narada mailbox JSONL record to an EmailMessage."""
    msg = EmailMessage()
    msg["Subject"] = str(rec.get("subject", ""))
    msg["From"] = str(rec.get("sender", ""))
    to_addrs = rec.get("to") or []
    if isinstance(to_addrs, str):
        to_addrs = [a.strip() for a in to_addrs.split(",") if a.strip()]
    if to_addrs:
        msg["To"] = ", ".join(str(a) for a in to_addrs)
    cc_addrs = rec.get("cc") or []
    if isinstance(cc_addrs, str):
        cc_addrs = [a.strip() for a in cc_addrs.split(",") if a.strip()]
    if cc_addrs:
        msg["Cc"] = ", ".join(str(a) for a in cc_addrs)
    date_val = rec.get("date", "")
    if date_val:
        from email.utils import formatdate
        try:
            ts = int(date_val)
            msg["Date"] = formatdate(timeval=ts, usegmt=True)
        except (ValueError, TypeError):
            msg["Date"] = str(date_val)
    msg_id = rec.get("message_id", "")
    if msg_id:
        msg["Message-ID"] = str(msg_id)
    body_text = rec.get("body", "")
    if body_text:
        msg.set_content(str(body_text), subtype="plain", charset="utf-8")
    else:
        msg.set_content("", subtype="plain", charset="utf-8")
    return msg


__all__ = ["NaradaImapServer"]
