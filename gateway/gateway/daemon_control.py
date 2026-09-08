"""Minimal REST control server for the gateway daemon (Phase 5).

:class:`ControlServer` exposes a tiny HTTP API over a plain TCP
socket on ``127.0.0.1`` so an operator or monitoring script can
query daemon status, trigger a poll, or reload the mapping.

Endpoints:

    GET  /status          → daemon status JSON
    POST /poll            → trigger one inbound poll
    POST /reload          → reload the identity mapping
    GET  /health          → ``{"ok": true}``

The server is single-threaded and blocking; it is only intended
for localhost control traffic.
"""

from __future__ import annotations

import json
import logging
import re
import select
import socket
import threading
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .daemon import GatewayDaemon

log = logging.getLogger("narada.daemon.control")


class ControlServer:
    """Tiny HTTP control server for the gateway daemon.

    Parameters
    ----------
    daemon:
        The :class:`GatewayDaemon` instance to control.
    host:
        Bind address (default ``127.0.0.1``).
    port:
        Bind port (default ``1144``).
    """

    def __init__(
        self,
        *,
        daemon: "GatewayDaemon",
        host: str = "127.0.0.1",
        port: int = 1144,
    ) -> None:
        self._daemon = daemon
        self._host = host
        self._port = port
        self._server_socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start_background(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._serve, daemon=True, name="narada-control"
        )
        self._thread.start()

    def shutdown(self) -> None:
        self._running = False
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _serve(self) -> None:
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.settimeout(1.0)
        try:
            self._server_socket.bind((self._host, self._port))
            self._server_socket.listen(5)
            log.info("Control server listening on %s:%d", self._host, self._port)
            while self._running:
                try:
                    client_sock, addr = self._server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                t = threading.Thread(
                    target=self._handle_request,
                    args=(client_sock,),
                    daemon=True,
                )
                t.start()
        except Exception as exc:
            log.error("Control server error: %s", exc)
        finally:
            self._running = False

    def _handle_request(self, sock: socket.socket) -> None:
        try:
            sock.settimeout(5.0)
            data = sock.recv(4096)
            if not data:
                return
            request = data.decode("utf-8", errors="replace")
            first_line = request.split("\r\n", 1)[0]
            parts = first_line.split(None, 2)
            if len(parts) < 2:
                self._send_response(sock, 400, {"error": "Bad request"})
                return
            method = parts[0].upper()
            path = parts[1]

            if method == "GET" and path == "/health":
                self._send_response(sock, 200, {"ok": True})
            elif method == "GET" and path == "/status":
                self._send_response(sock, 200, self._daemon.status())
            elif method == "POST" and path == "/poll":
                result = self._daemon.trigger_poll()
                self._send_response(sock, 200, result)
            elif method == "POST" and path == "/reload":
                result = self._daemon.reload_mapping()
                status = 200 if result.get("success") else 400
                self._send_response(sock, status, result)
            else:
                self._send_response(sock, 404, {"error": "Not found"})
        except Exception as exc:
            log.debug("Control request error: %s", exc)
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _send_response(
        self, sock: socket.socket, code: int, body: dict
    ) -> None:
        payload = json.dumps(body, default=str).encode("utf-8")
        status_text = {200: "OK", 400: "Bad Request", 404: "Not Found"}.get(
            code, "Error"
        )
        header = (
            f"HTTP/1.1 {code} {status_text}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode("utf-8")
        try:
            sock.sendall(header + payload)
        except Exception:
            pass


__all__ = ["ControlServer"]
