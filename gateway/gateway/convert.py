"""NaradaBody <-> RFC822 conversion (Phase 5).

The conversion is intentionally narrow: subject, sender, to, cc,
body_text, sent_at. Attachments, threading headers, HTML bodies,
and MIME multipart are out of scope for Phase 5.

The two functions are inverses for the MVP field set.
"""

from __future__ import annotations

import email.message
import email.utils
from email.message import EmailMessage
from typing import Iterable, Mapping, Sequence

from .errors import ConversionError


# Importing NaradaBody directly from the node package would create
# a hard dependency on the node runtime at import time. Phase 5
# uses a local typed-dict-equivalent dataclass instead, populated
# from a dict that callers build.
#
# We re-export the canonical NaradaBody dataclass when it is
# available (so existing node code can pass one in) and fall back
# to a local ``_NaradaBodyDict``-shaped view otherwise.

try:
    from node.src.narada.envelope import NaradaBody  # type: ignore
except Exception:  # pragma: no cover
    NaradaBody = None  # type: ignore


def narada_body_to_rfc822(
    body: Mapping[str, object],
    *,
    from_addr: str,
    to_addrs: Sequence[str],
    cc_addrs: Sequence[str] = (),
) -> EmailMessage:
    """Build an :class:`EmailMessage` from a Narada body view.

    Parameters
    ----------
    body:
        Either a ``NaradaBody`` dataclass (or any mapping) with
        the keys ``subject``, ``sender``, ``to``, ``cc``,
        ``body_text``, ``sent_at``.
    from_addr:
        Conventional ``From`` address. The caller has already
        resolved the Narada sender's id to this address via
        ``IdentityMapping``.
    to_addrs / cc_addrs:
        Conventional recipient addresses, already resolved.
    """
    msg = EmailMessage()
    msg["From"] = from_addr
    if to_addrs:
        msg["To"] = ", ".join(to_addrs)
    if cc_addrs:
        msg["Cc"] = ", ".join(cc_addrs)
    subject = _get_str(body, "subject", default="")
    if subject:
        msg["Subject"] = subject
    sent_at = _get_int(body, "sent_at", default=0)
    if sent_at:
        try:
            msg["Date"] = email.utils.formatdate(sent_at, usegmt=True)
        except (TypeError, ValueError) as exc:
            raise ConversionError(f"invalid sent_at: {sent_at!r}") from exc
    # Narada-side sender/to/cc are preserved in custom headers so
    # the round-trip can recover them on the inbound path.
    sender = _get_str(body, "sender", default="")
    if sender:
        msg["X-Narada-Sender"] = sender
    narada_to = _get_seq_str(body, "to")
    if narada_to:
        msg["X-Narada-To"] = ", ".join(narada_to)
    narada_cc = _get_seq_str(body, "cc")
    if narada_cc:
        msg["X-Narada-Cc"] = ", ".join(narada_cc)
    body_text = _get_str(body, "body_text", default="")
    msg.set_content(body_text, subtype="plain", charset="utf-8")
    return msg


def rfc822_to_narada_body(msg: EmailMessage | email.message.Message) -> dict:
    """Convert an RFC822 message into a dict shaped like a
    :class:`NaradaBody`.

    The result is a plain ``dict`` so the caller can hand it to
    ``NaradaBody.from_dict`` or feed it to the envelope builder
    without importing the node package at gateway import time.
    """
    if not isinstance(msg, (EmailMessage, email.message.Message)):
        raise ConversionError("rfc822_to_narada_body expects an email.message")
    sender = str(msg.get("X-Narada-Sender") or msg.get("From") or "")
    to_field = msg.get("X-Narada-To") or msg.get("To") or ""
    cc_field = msg.get("X-Narada-Cc") or msg.get("Cc") or ""
    subject = str(msg.get("Subject") or "")
    date_str = msg.get("Date")
    if date_str:
        try:
            sent_at = email.utils.parsedate_to_datetime(str(date_str))
            sent_at_int = int(sent_at.timestamp())
        except (TypeError, ValueError) as exc:
            raise ConversionError(f"invalid Date header: {date_str!r}") from exc
    else:
        sent_at_int = 0
    body_text = ""
    if msg.is_multipart():
        # MVP: prefer the first text/plain part. Phase 5 does not
        # ship HTML or attachments, but we still tolerate a
        # multipart wrapper so an off-the-shelf IMAP poll works.
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                try:
                    body_text = payload.decode(charset, errors="replace")
                except (LookupError, TypeError):
                    body_text = payload.decode("utf-8", errors="replace")
                break
    else:
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        try:
            body_text = payload.decode(charset, errors="replace")
        except (LookupError, TypeError):
            body_text = payload.decode("utf-8", errors="replace")
    return {
        "subject": subject,
        "sender": sender,
        "to": _split_addresses(to_field),
        "cc": _split_addresses(cc_field),
        "body_text": body_text,
        "sent_at": sent_at_int,
    }


# --- helpers ---------------------------------------------------------------


def _get_str(body: Mapping[str, object], key: str, *, default: str) -> str:
    value = body.get(key, default)
    if value is None:
        return default
    return str(value)


def _get_int(body: Mapping[str, object], key: str, *, default: int) -> int:
    value = body.get(key, default)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ConversionError(f"invalid int for {key!r}: {value!r}")



def _get_seq_str(body: Mapping[str, object], key: str) -> list[str]:
    value = body.get(key) or ()
    if isinstance(value, str):
        return _split_addresses(value)
    if isinstance(value, Iterable):
        return [str(x) for x in value if x]
    return []


def _split_addresses(value: str) -> list[str]:
    """Split a header-style comma-separated list. The MVP does
    not parse display names; we keep the raw address token."""
    out: list[str] = []
    for piece in str(value or "").split(","):
        token = piece.strip()
        if token:
            out.append(token)
    return out


__all__ = ["narada_body_to_rfc822", "rfc822_to_narada_body"]
