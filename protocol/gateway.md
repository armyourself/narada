# Narada ↔ SMTP Gateway (Phase 5)

> Status: **specified (Phase 5).** The Narada↔SMTP conversion
> contract, the identity-mapping format, and the boundary the
> gateway enforces are defined here. The implementation lives in
> `gateway/gateway/`.

## Goal

A Narada user should be able to email any conventional address
(`alice@gmail.com`) and any conventional address should be able
to email a Narada user (`bob@narada`), without the Narada user
having to run their own IMAP/SMTP server or share a password
with a third party.

```
Narada user (Bob)
        ▲
        │ Narada protocol (sealed envelope)
        │
┌───────┴───────┐
│ Narada Gateway │  ← this document
└───────┬───────┘
        │ RFC822 + SMTP (plaintext)
        ▼
Conventional email (Gmail, Outlook, ...)
        ▲
        │
        │ SMTP submit
        ▼
Bob's gateway inbox (IMAP)
```

The gateway is the trust boundary. Everything inside the Narada
network is sealed-and-signed; everything outside is conventional
RFC822 plaintext.

## Threat model (Phase 5 scope)

The gateway is honest-but-curious. It can:

* see plaintext for every message it routes (RFC822 is plaintext);
* be configured to refuse to forward without a mapping (no open relay);
* fail closed on any mapping ambiguity.

It **cannot**:

* forge a Narada-side identity it does not hold (sealing requires
  the recipient's private key);
* decrypt Narada-side traffic that wasn't addressed to one of its
  configured local identities;
* bypass the identity-mapping table.

Out of scope for Phase 5: spam filtering, rate limits, reputation,
SRS, DKIM/SPF alignment, DANE, MTA-STS, onion-relay anonymity. The
gateway is research-grade; production hardening lands with the
Phase 6 audit.

## Wire surface

### Narada → SMTP (outbound)

1. The gateway receives a sealed Narada envelope addressed to a
   conventional recipient (the gateway is in the recipient's
   `narada1...` set, or a relay forwards to it).
2. The gateway opens the envelope with the local recipient
   identity and gets a `NaradaBody` (subject, sender, to, cc,
   body_text, sent_at).
3. The gateway maps the Narada recipient's `narada1...` id to a
   conventional address via `IdentityMapping.lookup_narada_to_smtp`
   and refuses the send if no mapping exists.
4. The gateway builds an RFC822 message (`email.message.EmailMessage`)
   with `From` = the conventional address of the Narada sender
   (mapped), `To`/`Cc` = the conventional recipients (mapped),
   `Subject` = `NaradaBody.subject`, body = `NaradaBody.body_text`.
5. The gateway submits the message via `SmtpSender` (which
   delegates to the existing Openmail `SMTPManager`).
6. The gateway returns a `NaradaAck` to the original sender
   carrying the conventional SMTP transaction's response code
   (best-effort; a missing ack does not invalidate delivery).

### SMTP → Narada (inbound)

1. The gateway polls a conventional IMAP mailbox
   (`ImapReceiver.fetch_unseen`).
2. Each unseen message is parsed into a `NaradaBody` with
   subject, sender, to, cc, body_text, sent_at.
3. The gateway maps the conventional sender to a Narada public
   id via `IdentityMapping.lookup_smtp_to_narada` and refuses the
   ingestion if no mapping exists (no anonymous inbound into Narada).
4. The gateway builds a sealed `NaradaEnvelope` addressed to the
   local Narada recipient and persists it via the Narada
   inbox path.
5. The original IMAP message is marked `\Seen`.

The Phase-5 deliverable ships the conversion + mapping +
`SmtpSender` / `ImapReceiver` adapters and exercises the
conversion in tests; live connectivity to a real SMTP/IMAP
server is held to a follow-up.

## Identity mapping

A single JSON file per gateway instance:

```json
{
  "narada_to_smtp": {
    "narada1qalice...": "alice@example.com",
    "narada1qbob...":   "bob@example.com"
  },
  "smtp_to_narada": {
    "alice@example.com": "narada1qalice...",
    "bob@example.com":   "narada1qbob..."
  }
}
```

* `narada_to_smtp` is consulted on outbound (Narada → SMTP).
* `smtp_to_narada` is consulted on inbound (SMTP → Narada).
* A `narada1...` value may appear in both maps.
* A conventional address may map to **exactly one** Narada id
  (Phase 5 invariant). Aliases are out of scope.
* A mapping **must** exist on the path being used; missing
  mappings are refused (no open relay, no anonymous inbound).

The file is loaded on startup and reloaded on `SIGHUP` (or via
an explicit `reload()` call from the integration test).

## Conversion (NaradaBody ↔ RFC822)

`gateway/gateway/convert.py` exposes:

* `narada_body_to_rfc822(body, *, from_addr, to_addrs, cc_addrs=())`
  -> `email.message.EmailMessage`
* `rfc822_to_narada_body(msg)` -> `NaradaBody`

The two are inverse for the MVP field set: subject, sender, to,
cc, body_text, sent_at. Attachments, threading (`In-Reply-To`,
`References`), HTML bodies, and MIME multipart are **out of scope
for Phase 5** — Phase 5 carries plain text only. The conversion
preserves `NaradaBody.sent_at` as the RFC822 `Date` header (Unix
seconds → RFC822 date format) and round-trips the message-id
when present (`Message-ID: <uuid>@narada.local`).

## Adapters

`SmtpSender` and `ImapReceiver` are thin wrappers around the
existing Openmail `SMTPManager` and `IMAPManager`. They live in
`gateway/gateway/sender.py` and `receiver.py` so the gateway
package does not duplicate Openmail's connection logic.

For tests, both adapters accept a `transport` callable (a
function that takes the RFC822 bytes and returns a
`(success: bool, response: str)` tuple). The default is the
real Openmail client; tests pass an in-memory recorder.

## Out of scope (Phase 5)

* IMAP → Narada bulk ingest (the IMAP *server* path, exposing a
  Narada mailbox over IMAP for legacy clients).
* Narada → IMAP (legacy clients pulling a Narada mailbox).
* Spam filtering, greylisting, reputation.
* SRS, DKIM signing, SPF alignment.
* DANE, MTA-STS.
* Onion-relay anonymity for the SMTP leg.
* Live end-to-end smoke against Gmail / Outlook (held until the
  operator story is clearer and the audit is done).
