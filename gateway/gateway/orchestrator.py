"""High-level gateway orchestrator (Phase 5).

:class:`Gateway` ties the mapping, conversion, sender, and
receiver into two directions:

* :meth:`Gateway.deliver_outbound` takes a Narada body view and
  ships it as conventional SMTP mail.
* :meth:`Gateway.poll_inbound` polls the configured IMAP mailbox
  and yields ``(narada_recipient_id, narada_body_dict)`` pairs
  the caller can wrap in a sealed envelope and persist via the
  Narada inbox path.

The orchestrator deliberately has **no Narada-protocol knowledge
beyond the body shape** — it produces RFC822 bytes and accepts
RFC822 bytes. Sealing / unsealing lives in the node runtime
(``src.narada.envelope``).
"""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from typing import Callable, Iterable, Mapping, Optional

from .convert import narada_body_to_rfc822, rfc822_to_narada_body
from .errors import ConversionError, NoMappingError
from .mapping import IdentityMapping
from .receiver import ImapReceiver
from .sender import SmtpSender


@dataclass(frozen=True)
class InboundItem:
    """One inbound message the gateway has converted."""

    narada_recipient_id: str
    body: dict
    rfc822: EmailMessage


class Gateway:
    """The Narada <-> conventional-email gateway."""

    def __init__(
        self,
        *,
        mapping: IdentityMapping,
        sender: SmtpSender,
        receiver: Optional[ImapReceiver] = None,
    ) -> None:
        self._mapping = mapping
        self._sender = sender
        self._receiver = receiver

    @property
    def mapping(self) -> IdentityMapping:
        return self._mapping

    @property
    def sender(self) -> SmtpSender:
        return self._sender

    @property
    def receiver(self) -> Optional[ImapReceiver]:
        return self._receiver

    # --- Outbound (Narada -> SMTP) ------------------------------------

    def deliver_outbound(
        self,
        *,
        narada_recipient_id: str,
        body: Mapping[str, object],
    ) -> tuple[bool, str]:
        """Ship ``body`` to the conventional address mapped from
        ``narada_recipient_id``.

        Returns ``(True, response)`` on success. Raises
        :class:`NoMappingError` if no mapping exists or
        :class:`ConversionError` / :class:`SmtpSendError` on
        downstream failures.
        """
        smtp_recipient = self._mapping.lookup_narada_to_smtp(narada_recipient_id)
        # The Narada sender is whatever the body says it is; the
        # gateway maps that to a conventional address too so the
        # SMTP ``From`` is honest.
        narada_sender = str(body.get("sender") or "")
        smtp_sender = ""
        if narada_sender:
            try:
                smtp_sender = self._mapping.try_lookup_narada_to_smtp(
                    _extract_narada_id(narada_sender) or ""
                ) or ""
            except NoMappingError:
                smtp_sender = ""
        cc_addrs: list[str] = []
        for ccid in body.get("cc") or ():
            try:
                smtp_ccid = self._mapping.lookup_narada_to_smtp(str(ccid))
            except NoMappingError:
                # Phase 5 is strict: every cc must resolve. A
                # silent drop would let a sender reach a recipient
                # they did not intend to cc.
                raise
            cc_addrs.append(smtp_ccid)
        msg = narada_body_to_rfc822(
            body,
            from_addr=smtp_sender or str(self._sender._smtp_from),
            to_addrs=[smtp_recipient],
            cc_addrs=cc_addrs,
        )
        return self._sender.send(msg)

    # --- Inbound (SMTP -> Narada) -------------------------------------

    def poll_inbound(self) -> list[InboundItem]:
        """Poll the configured IMAP mailbox and convert each unseen
        message into an :class:`InboundItem`.

        Messages whose sender is not in the mapping are dropped
        (no anonymous inbound into Narada).
        """
        if self._receiver is None:
            raise ConversionError("no IMAP receiver configured")
        items: list[InboundItem] = []
        for rfc822 in self._receiver.fetch():
            narada_sender_id = _extract_narada_id(str(rfc822.get("From") or ""))
            if narada_sender_id is None:
                # Conventional-only From — look it up in the
                # mapping to learn the Narada identity.
                try:
                    narada_sender_id = self._mapping.lookup_smtp_to_narada(
                        _extract_email(str(rfc822.get("From") or ""))
                    )
                except NoMappingError:
                    # Drop anonymous inbound silently.
                    continue
            narada_to_ids: list[str] = []
            for addr in _addresses(rfc822, "To"):
                try:
                    narada_to_ids.append(
                        self._mapping.lookup_smtp_to_narada(addr)
                    )
                except NoMappingError:
                    continue
            for addr in _addresses(rfc822, "Cc"):
                try:
                    narada_to_ids.append(
                        self._mapping.lookup_smtp_to_narada(addr)
                    )
                except NoMappingError:
                    continue
            if not narada_to_ids:
                # No recipient we can deliver to. Drop.
                continue
            body = rfc822_to_narada_body(rfc822)
            # The Narada side sees a single primary recipient for
            # persistence purposes; the gateway picks the first
            # mapped id. Callers can fan-out if needed.
            items.append(
                InboundItem(
                    narada_recipient_id=narada_to_ids[0],
                    body=body,
                    rfc822=rfc822,
                )
            )
        return items


# --- helpers ---------------------------------------------------------------


def _addresses(msg: EmailMessage, header: str) -> Iterable[str]:
    raw = msg.get(header)
    if not raw:
        return ()
    out = []
    for piece in str(raw).split(","):
        token = piece.strip()
        if token:
            out.append(token)
    return out


def _extract_email(value: str) -> str:
    """Return the bare email token from ``Name <addr@x>``."""
    if "<" in value and ">" in value:
        inside = value.split("<", 1)[1].split(">", 1)[0]
        return inside.strip().lower()
    return value.strip().lower()


def _extract_narada_id(value: str) -> Optional[str]:
    """Return the embedded ``narada1...`` id if any. Phase 5's
    Narada sender is rendered as ``Name <narada1...@gateway>``
    or simply the bare id."""
    token = value.strip()
    if token.startswith("narada1"):
        return token
    if "<" in token and ">" in token:
        inside = token.split("<", 1)[1].split(">", 1)[0]
        if inside.startswith("narada1"):
            return inside
    return None


__all__ = ["Gateway", "InboundItem"]
