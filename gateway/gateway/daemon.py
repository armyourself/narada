"""Long-running Narada gateway daemon (Phase 5).

:class:`GatewayDaemon` ties together the SMTP sender, IMAP receiver,
identity mapping, and the optional IMAP server into a long-running
process that:

1. Polls IMAP on a configurable interval and converts inbound
   messages into Narada format.
2. Exposes a minimal REST control API (status, manual poll,
   mapping reload).
3. Optionally runs a Narada -> IMAP server so legacy clients
   can read the Narada mailbox.

Usage::

    daemon = GatewayDaemon(
        mapping_path=Path("mapping.json"),
        smtp_host="smtp.example.com",
        imap_host="imap.example.com",
        ...
    )
    daemon.run()  # blocks
"""

from __future__ import annotations

import json
import logging
import signal
import threading
import time
from pathlib import Path
from typing import Optional

from .daemon_control import ControlServer
from .imap_server import NaradaImapServer
from .ingester import ImapIngester, IngestResult
from .mapping import IdentityMapping
from .orchestrator import Gateway
from .receiver import ImapReceiver
from .sender import SmtpSender

log = logging.getLogger("narada.daemon")


class GatewayDaemon:
    """The long-running gateway daemon.

    Parameters
    ----------
    mapping_path:
        Path to the identity-mapping JSON file.  The daemon
        re-reads this on ``reload_mapping``.
    data_dir:
        Narada node data directory.
    smtp_host / smtp_port / smtp_user / smtp_password / smtp_from:
        SMTP connection parameters.
    imap_host / imap_port / imap_user / imap_password / imap_folder:
        IMAP connection parameters for inbound polling.
    poll_interval:
        Seconds between inbound polls.
    imap_server_port:
        If set, the daemon also runs a Narada -> IMAP server on
        this port (default *None* = disabled).
    control_port:
        Port for the control REST API (default 1144).
    """

    def __init__(
        self,
        *,
        mapping_path: Path,
        data_dir: Optional[Path] = None,
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        smtp_from: str = "",
        imap_host: str = "",
        imap_port: int = 993,
        imap_user: str = "",
        imap_password: str = "",
        imap_folder: str = "INBOX",
        poll_interval: float = 300.0,
        imap_server_port: Optional[int] = None,
        control_port: int = 1144,
    ) -> None:
        self._mapping_path = Path(mapping_path)
        self._data_dir = Path(data_dir) if data_dir else Path.home() / ".openmail"
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_password = smtp_password
        self._smtp_from = smtp_from
        self._imap_host = imap_host
        self._imap_port = imap_port
        self._imap_user = imap_user
        self._imap_password = imap_password
        self._imap_folder = imap_folder
        self._poll_interval = poll_interval
        self._imap_server_port = imap_server_port
        self._control_port = control_port

        self._mapping: Optional[IdentityMapping] = None
        self._gateway: Optional[Gateway] = None
        self._ingester: Optional[ImapIngester] = None
        self._imap_server: Optional[NaradaImapServer] = None
        self._control: Optional[ControlServer] = None
        self._running = False
        self._last_poll: Optional[float] = None
        self._last_result: Optional[IngestResult] = None
        self._poll_count = 0

    # --- Lifecycle --------------------------------------------------------

    def run(self) -> None:
        """Start the daemon and block until interrupted."""
        self._running = True
        self._load_mapping()
        self._build_components()

        # Install signal handlers.
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        # Start the IMAP server if configured.
        if self._imap_server_port is not None:
            self._imap_server = NaradaImapServer(
                data_dir=self._data_dir,
                host="127.0.0.1",
                port=self._imap_server_port,
            )
            self._imap_server.start_background()
            log.info("Narada IMAP server started on port %d", self._imap_server_port)

        # Start the control server.
        self._control = ControlServer(
            daemon=self,
            host="127.0.0.1",
            port=self._control_port,
        )
        self._control.start_background()
        log.info("Control API listening on port %d", self._control_port)

        log.info(
            "Gateway daemon started (poll interval: %.0fs)",
            self._poll_interval,
        )

        # Main polling loop.
        try:
            while self._running:
                self._do_poll()
                self._sleep(self._poll_interval)
        except KeyboardInterrupt:
            pass
        finally:
            self._shutdown()

    def _handle_signal(self, signum, frame) -> None:
        log.info("Received signal %d, shutting down...", signum)
        self._running = False

    def _shutdown(self) -> None:
        self._running = False
        if self._imap_server is not None:
            self._imap_server.shutdown()
        if self._control is not None:
            self._control.shutdown()
        log.info("Gateway daemon stopped")

    def _sleep(self, seconds: float) -> None:
        """Interruptible sleep."""
        end = time.monotonic() + seconds
        while self._running and time.monotonic() < end:
            time.sleep(min(1.0, end - time.monotonic()))

    # --- Core operations --------------------------------------------------

    def _load_mapping(self) -> None:
        self._mapping = IdentityMapping.from_file(self._mapping_path)
        log.info(
            "Mapping loaded: %d narada ids, %d smtp addresses",
            len(self._mapping.narada_ids()),
            len(self._mapping.smtp_addresses()),
        )

    def _build_components(self) -> None:
        """Build or rebuild the gateway, ingester, and related state.

        Called once at startup and again after ``reload_mapping``.
        """
        sender = SmtpSender(
            smtp_host=self._smtp_host,
            smtp_port=self._smtp_port,
            username=self._smtp_user,
            password=self._smtp_password,
            smtp_from=self._smtp_from,
        )
        receiver = ImapReceiver(
            imap_host=self._imap_host,
            imap_port=self._imap_port,
            username=self._imap_user,
            password=self._imap_password,
            folder=self._imap_folder,
        )
        self._gateway = Gateway(
            mapping=self._mapping,
            sender=sender,
            receiver=receiver,
        )
        self._ingester = ImapIngester(
            mapping=self._mapping,
            data_dir=self._data_dir,
            fetch=receiver.fetch,
        )

    def _do_poll(self) -> IngestResult:
        """Execute one inbound poll cycle."""
        self._poll_count += 1
        self._last_poll = time.time()
        if self._ingester is None:
            result = IngestResult()
            self._last_result = result
            return result
        try:
            result = self._ingester.ingest()
            self._last_result = result
            if result.imported > 0:
                log.info(
                    "Poll #%d: imported %d, skipped %d, errors %d",
                    self._poll_count,
                    result.imported,
                    result.skipped,
                    result.errors,
                )
            return result
        except Exception as exc:
            log.error("Poll #%d failed: %s", self._poll_count, exc)
            result = IngestResult(errors=1)
            self._last_result = result
            return result

    # --- Control API helpers -----------------------------------------------

    def reload_mapping(self) -> dict:
        """Reload the identity mapping from disk. Returns status."""
        try:
            self._load_mapping()
            self._build_components()
            return {
                "success": True,
                "narada_ids": len(self._mapping.narada_ids()),
                "smtp_addresses": len(self._mapping.smtp_addresses()),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def status(self) -> dict:
        """Return daemon status."""
        return {
            "running": self._running,
            "poll_count": self._poll_count,
            "last_poll": self._last_poll,
            "last_result": {
                "imported": self._last_result.imported,
                "skipped": self._last_result.skipped,
                "errors": self._last_result.errors,
            }
            if self._last_result
            else None,
            "imap_server_port": self._imap_server_port,
            "control_port": self._control_port,
            "mapping": {
                "narada_ids": len(self._mapping.narada_ids()) if self._mapping else 0,
                "smtp_addresses": len(self._mapping.smtp_addresses()) if self._mapping else 0,
            },
        }

    def trigger_poll(self) -> dict:
        """Manually trigger one poll cycle. Returns the result."""
        result = self._do_poll()
        return {
            "imported": result.imported,
            "skipped": result.skipped,
            "errors": result.errors,
        }


__all__ = ["GatewayDaemon"]
