"""SMTP outbound adapter for the gateway (Phase 5).

Wraps the existing Openmail ``SMTPManager`` so the gateway does
not duplicate connection logic. The adapter accepts an optional
``transport`` callable for tests; the default delegates to
``node.src.modules.openmail.smtp.SMTPManager.send_email``.
"""

from __future__ import annotations

from email.message import EmailMessage
from typing import Callable, Optional, Sequence

from .errors import SmtpSendError


SmtpTransport = Callable[[EmailMessage], tuple[bool, str]]


def default_transport(
    *,
    smtp_host: str,
    smtp_port: int,
    username: str,
    password: str,
) -> SmtpTransport:
    """Build the default SMTP transport backed by ``SMTPManager``.

    Returns a closure that sends a single ``EmailMessage`` via a
    fresh ``SMTPManager`` instance. Tests use a recorder closure
    instead.
    """

    def _send(msg: EmailMessage) -> tuple[bool, str]:
        try:
            from node.src.modules.openmail.smtp import SMTPManager  # type: ignore
            from node.src.modules.openmail.types import Draft  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise SmtpSendError(
                "SMTPManager import failed; the node runtime is required"
            ) from exc
        draft = Draft(
            sender=username,
            receivers=[str(a) for a in (msg.get_all("To") or [])],
            subject=str(msg.get("Subject") or ""),
            body=msg.get_content() if not msg.is_multipart() else "",
        )
        try:
            client = SMTPManager(username, password, host=smtp_host, port=smtp_port)
        except Exception as exc:
            raise SmtpSendError(f"smtp connect failed: {exc}") from exc
        try:
            ok, response = client.send_email(draft)
        finally:
            try:
                client.logout()
            except Exception:
                pass
        if not ok:
            raise SmtpSendError(f"smtp refused: {response}")
        return True, response

    return _send


class SmtpSender:
    """Outbound SMTP adapter for the gateway.

    Parameters
    ----------
    transport:
        A callable ``(EmailMessage) -> (ok, response)``. The
        default constructor uses
        :func:`default_transport` with the supplied credentials.
    smtp_from:
        The conventional ``From`` address to use when the
        caller did not already set one on the message.
    """

    def __init__(
        self,
        *,
        transport: Optional[SmtpTransport] = None,
        smtp_host: str = "",
        smtp_port: int = 587,
        username: str = "",
        password: str = "",
        smtp_from: str = "",
    ) -> None:
        if transport is None:
            self._transport = default_transport(
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                username=username,
                password=password,
            )
        else:
            self._transport = transport
        self._smtp_from = smtp_from

    def send(self, msg: EmailMessage) -> tuple[bool, str]:
        if self._smtp_from and not msg.get("From"):
            msg["From"] = self._smtp_from
        return self._transport(msg)


__all__ = ["SmtpSender", "SmtpTransport", "default_transport"]
