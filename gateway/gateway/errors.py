"""Errors raised by the Narada gateway."""


class GatewayError(Exception):
    """Base class for gateway failures."""


class NoMappingError(GatewayError):
    """Raised when the identity mapping table has no entry for the
    address being translated."""


class ConversionError(GatewayError):
    """Raised when a Narada <-> RFC822 conversion fails (missing
    required field, unparseable Date, etc.)."""


class SmtpSendError(GatewayError):
    """Raised when the SMTP adapter refuses a send (transport
    failure, auth failure, refused recipient)."""


class ImapFetchError(GatewayError):
    """Raised when the IMAP adapter cannot fetch messages."""


class ImapMarkError(GatewayError):
    """Raised when the IMAP adapter cannot mark messages as seen."""


__all__ = [
    "ConversionError",
    "GatewayError",
    "ImapFetchError",
    "ImapMarkError",
    "NoMappingError",
    "SmtpSendError",
]
