"""
Openmail
This module provides the Openmail class, which offers a simplified interface
for managing email operations via IMAP and SMTP protocols.

Dependencies:
- Requires `IMAPManager` and `SMTPManager` classes from the `imap` and
`smtp` modules.

Author: <berkaykayaforbusiness@outlook.com>
"""

import threading
from .imap import IMAPManager, IMAPManagerException
from .smtp import SMTPManager, SMTPManagerException
from src.helpers.uvicorn_logger import UvicornLogger

uvicorn_logger = UvicornLogger()

_AUTH_ERROR_MARKERS = (
    "authenticationfailed",
    "invalid credentials",
    "username and password not accepted",
    "authentication failed",
    "invalid login",
    "login failed",
    "invalid password",
    "(535",
    "(534",
    "(530",
    "lookup failed",
)


def _friendly_connection_error(technical: str) -> str:
    """Translate raw IMAP/SMTP failures into a message a non-technical user understands.

    Technical details are logged server-side; the caller only ever sees this text.
    """
    lowered = technical.lower()
    if any(marker in lowered for marker in _AUTH_ERROR_MARKERS):
        return (
            "Wrong email address or password. Please check them and try again. "
            "Note: Gmail and some other providers do not accept your normal password here - "
            "create an app password (Google Account > Security > 2-Step Verification > "
            "App Passwords) and use that instead."
        )
    return (
        "Could not reach the email server. Please check your internet connection "
        "and try again."
    )

class Openmail:
    """
    A high-level email management class that provides a unified interface
    for IMAP and SMTP operations.

    This class encapsulates email connection, sending, receiving,
    and folder management functionality using underlying IMAP and SMTP classes.
    """

    def __init__(self):
        """
        Initialize the Openmail class.

        Connections will be established when connect() method is called.
        """
        self._imap = None
        self._smtp = None

    @property
    def imap(self) -> IMAPManager:
        """Get the IMAPManager instance."""
        if not self._imap:
            raise IMAPManagerException(
                "IMAP connection is not established. Please call the 'connect' method first."
            )
        return self._imap

    @property
    def smtp(self) -> SMTPManager:
        """Get the SMTPManager instance."""
        if not self._smtp:
            raise SMTPManagerException(
                "SMTP connection is not established. Please call the 'connect' method first."
            )
        return self._smtp

    def connect(
        self,
        email_address: str,
        password: str,
        /,
        *,
        imap_host: str = "",
        imap_port: int = 993,
        imap_ssl_context=None,
        imap_enable_idle_optimization=False,
        imap_listen_new_messages=False,
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_local_hostname: str | None = None,
        timeout: int = 30,
    ) -> tuple[bool, str]:
        """
        Establish connections to IMAP and SMTP servers.

        Args:
            email_address (str): Email account username/address
            password (str): Email account password
            imap_host (str, optional): IMAP server hostname. Defaults to "".
            imap_port (int, optional): IMAP server port. Defaults to 993.
            smtp_host (str, optional): SMTP server hostname. Defaults to "".
            smtp_port (int, optional): SMTP server port. Defaults to 587.
            try_limit (int, optional): Number of connection retry attempts. Defaults to 3.
            timeout (int, optional): Connection timeout in seconds. Defaults to 30.

        Returns:
            tuple[bool, str]: A tuple containing connection status (True/False)
                               and a status message
        """
        def setup_imap():
            try:
                self._imap = IMAPManager(
                    email_address,
                    password,
                    imap_host,
                    imap_port,
                    ssl_context=imap_ssl_context,
                    timeout=timeout,
                    enable_idle_optimization=imap_enable_idle_optimization,
                    listen_new_messages=imap_listen_new_messages,
                )
            except Exception as e:
                self._imap = None
                setup_errors.append(f"IMAP connection failed: {e}")

        def setup_smtp():
            try:
                self._smtp = SMTPManager(
                    email_address, password, smtp_host, smtp_port, smtp_local_hostname, timeout
                )
            except Exception as e:
                self._smtp = None
                setup_errors.append(f"SMTP connection failed: {e}")

        setup_errors: list[str] = []

        imap_thread = threading.Thread(target=setup_imap)
        smtp_thread = threading.Thread(target=setup_smtp)

        imap_thread.start()
        smtp_thread.start()

        imap_thread.join()
        smtp_thread.join()

        if setup_errors:
            technical = "; ".join(setup_errors)
            uvicorn_logger.error(f"Email connection failed for {email_address}: {technical}")
            return False, _friendly_connection_error(technical)

        return True, "Connected successfully"

    def disconnect(self) -> tuple[bool, str]:
        """
        Close both IMAP and SMTP connections in parallel using threads.
        """
        imap_stat = smtp_stat = True
        imap_error = smtp_error = None

        def disconnect_imap():
            nonlocal imap_stat, imap_error
            try:
                if self.imap:
                    imap_stat, _ = self.imap.logout()
            except IMAPManagerException as e:
                imap_stat = "timeout" in str(e).lower()
                imap_error = str(e)
            except Exception as e:
                imap_stat = False
                imap_error = str(e)

        def disconnect_smtp():
            nonlocal smtp_stat, smtp_error
            try:
                if self.smtp:
                    smtp_stat, _ = self.smtp.logout()
            except SMTPManagerException as e:
                smtp_stat = "timeout" in str(e).lower()
                smtp_error = str(e)
            except Exception as e:
                smtp_stat = False
                smtp_error = str(e)

        # Thread'leri başlat
        imap_thread = threading.Thread(target=disconnect_imap)
        smtp_thread = threading.Thread(target=disconnect_smtp)

        imap_thread.start()
        smtp_thread.start()

        imap_thread.join()
        smtp_thread.join()

        # Hata mesajı oluştur
        disconnect_msg = ""
        if not imap_stat:
            disconnect_msg = "IMAP connection could not be terminated properly."
            if imap_error:
                disconnect_msg += f" Reason: {imap_error}"
        if not smtp_stat:
            disconnect_msg += "\nSMTP connection could not be terminated properly."
            if smtp_error:
                disconnect_msg += f" Reason: {smtp_error}"

        if disconnect_msg:
            return False, disconnect_msg

        return True, "Disconnected successfully."


__all__ = ["Openmail"]
