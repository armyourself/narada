import asyncio
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import unquote
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Form, UploadFile
from pydantic import BaseModel
from typing import Optional, Annotated, TypeVar

from src._types import Response
from src.utils import err_msg, safe_json_loads
from src.internal.account_manager import AccountManager
from src.internal.client_handler import ClientHandler
from src.internal.nostr_handler import NostrHandler
from src.helpers.uvicorn_logger import UvicornLogger
from src.modules.openmail.types import Email, Mailbox, Folder, Draft, Attachment, SearchCriteria
from src.modules.openmail.utils import extract_email_address

client_handler = ClientHandler()
nostr_handler = NostrHandler()
account_manager = AccountManager()
uvicorn_logger = UvicornLogger()

T = TypeVar("T")
OpenmailTaskResults = dict[str, T]

NEW_EMAIL_CHECK_INTERVAL_SEC = 60

router = APIRouter(
    tags=["Mailbox"]
)

def check_openmail_connection_availability(
    account: str,
    for_new_messages: bool = False
) -> Response | bool:
    print("Checking for connection availability: ", account)
    connection_result = client_handler.is_connection_available(account, for_new_messages)
    if isinstance(connection_result, bool) and connection_result:
        return True

    return Response(
        success=False,
        message=f'Error, {account} connection is not available or timed out and could not reconnected.'
    )

@router.websocket("/notifications/{account}")
async def notifications_socket(websocket: WebSocket, account: str):
    await websocket.accept()
    uvicorn_logger.websocket(websocket, "New notification subscription created")
    try:
        while True:
            account = extract_email_address(account)
            if client_handler.is_client_exists(account, True):
                response = check_openmail_connection_availability(account, True)
                if isinstance(response, Response):
                    await websocket.close(reason=response.message)
                    uvicorn_logger.websocket(websocket, response.message)
                    break
            else:
                account = account_manager.get(account)
                if account:
                    client_handler.connect_to_account(account, True)
                else:
                    reason = f"There is no account with {account} email address."
                    await websocket.close(reason=reason)
                    uvicorn_logger.websocket(websocket, reason)
                    break

            # Listen for new messages and send notification when
            # any new message received.
            while True:
                try:
                    await asyncio.sleep(NEW_EMAIL_CHECK_INTERVAL_SEC)
                    print(f"Checking for new emails for {account}")
                    openmail_client = client_handler.get_client(account, True)
                    if openmail_client.imap.any_new_email():
                        print(f"Account {account} has new emails")
                        recent_emails = openmail_client.imap.get_recent_emails()
                        await websocket.send_json({account: recent_emails})
                        uvicorn_logger.websocket(websocket, recent_emails)
                except Exception as e:
                    await websocket.close(reason="There was an error while receving new emails.")
                    uvicorn_logger.websocket(websocket, e)
                    break
    except WebSocketDisconnect:
        pass

@router.get("/get-hierarchy-delimiter/{account}")
async def get_hierarchy_delimiter(
    account: str
) -> Response[OpenmailTaskResults[str]]:
    try:
        account = extract_email_address(account)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        return Response(
            success=True,
            message="IMAP hierarchy delimiter found successfully.",
            data={account: client_handler.get_client(account).imap.hierarchy_delimiter}
        )
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while getting IMAP hierarchy delimiter", str(e)))

@router.get("/search-emails/{account}")
async def search_emails(
    account: str,
    folder: Optional[str] = None,
    search: Optional[str] = None,
) -> Response[OpenmailTaskResults[list[str]]]:
    try:
        account = extract_email_address(account)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        search_criteria = search or ""
        if search_criteria:
            search_loaded = safe_json_loads(search_criteria)
            if isinstance(search_loaded, dict):
                search_criteria = SearchCriteria(**search_loaded)

        return Response(
            success=True,
            message="Emails searched successfully.",
            data={account: client_handler.get_client(account).imap.search_emails(folder, search_criteria)}
        )
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while searching emails.", str(e)))

NOSTR_RECORD_PAGE_LIMIT = 5000


def _is_native_nostr_address(value: str) -> bool:
    """True for a raw Nostr id (hex pubkey or npub), not an email address."""
    candidate = (value or "").strip()
    if "<" in candidate and ">" in candidate:
        candidate = candidate.split("<", 1)[1].split(">", 1)[0].strip()
    if candidate.lower().startswith("npub1"):
        return True
    return len(candidate) == 64 and all(
        c in "0123456789abcdefABCDEF" for c in candidate
    )


def _email_route(source: str | None, sender: str) -> str:
    """Classify how an email travelled.

    - gateway: conventional email over IMAP/SMTP
    - direct:  native Nostr identity -> native Nostr identity
    - relay:   Nostr transport carrying a conventional address
    """
    if source != "nostr":
        return "gateway"
    return "direct" if _is_native_nostr_address(sender) else "relay"


def _email_timestamp(value: str | None) -> float:
    """Best-effort unix timestamp for sorting mixed date formats."""
    text = (value or "").strip()
    if not text:
        return 0.0
    if text.isdigit():
        return float(text)
    try:
        return float(text)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text).timestamp()
    except Exception:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except Exception:
        return 0.0


def _parse_search_criteria(search: str | None) -> SearchCriteria | str:
    """Parse the optional ``search`` query parameter."""
    if not search:
        return ""
    loaded = safe_json_loads(search)
    if isinstance(loaded, dict):
        return SearchCriteria(**loaded)
    return search


def _nostr_record_matches(record: dict, criteria: SearchCriteria) -> bool:
    """Apply SearchCriteria to a local Nostr mailbox record.

    Size bounds (smaller_than/larger_than) are skipped: the JSONL
    records carry no size metadata.
    """
    sender = str(record.get("sender", "")).lower()
    subject = str(record.get("subject", "")).lower()
    body = str(record.get("body", "")).lower()
    receivers = ", ".join(record.get("to") or []).lower()
    cc = ", ".join(record.get("cc") or []).lower()
    flags = [str(f).lower() for f in (record.get("flags") or [])]
    text = f"{subject} {body}"

    if criteria.senders and not any(s.lower() in sender for s in criteria.senders):
        return False
    if criteria.receivers and not any(
        r.lower() in receivers for r in criteria.receivers
    ):
        return False
    if criteria.cc and not any(c.lower() in cc for c in criteria.cc):
        return False
    if criteria.subject and criteria.subject.lower() not in subject:
        return False
    if criteria.include and criteria.include.lower() not in text:
        return False
    if criteria.exclude and criteria.exclude.lower() in text:
        return False
    if criteria.has_attachments and not record.get("attachments"):
        return False
    if criteria.included_flags and not all(
        flag in flags for flag in (f.lower() for f in criteria.included_flags)
    ):
        return False
    if criteria.excluded_flags and any(
        flag in flags for flag in (f.lower() for f in criteria.excluded_flags)
    ):
        return False

    sent_at = _email_timestamp(str(record.get("date", "")))
    if criteria.since:
        since = _email_timestamp(criteria.since)
        if since and sent_at and sent_at < since:
            return False
    if criteria.before:
        before = _email_timestamp(criteria.before)
        if before and sent_at and sent_at >= before:
            return False
    return True


def _nostr_record_to_email(record: dict) -> Email:
    """Project a Nostr mailbox record onto the shared Email model."""
    sender = str(record.get("sender", ""))
    return Email(
        message_id=str(
            record.get("message_id") or f"<{record.get('uid', '')}@nostr>"
        ),
        uid=str(record.get("uid", "")),
        sender=sender,
        receivers=str(record.get("receivers", "")),
        date=str(record.get("date", "")),
        subject=str(record.get("subject", "")),
        body=str(record.get("body", "")),
        flags=list(record.get("flags") or []),
        source="nostr",
        route=_email_route("nostr", sender),
    )


SEARCH_ALL_MAX_RESULTS = 200


class SearchAllRequest(BaseModel):
    query: str = ""
    criteria: Optional[dict] = None
    accounts: Optional[list[str]] = None
    folder: Optional[str] = None
    limit: int = SEARCH_ALL_MAX_RESULTS


def _search_all_accounts(requested: Optional[list[str]]) -> list[str]:
    """Union of every known account, or the caller's subset (order kept)."""
    if requested:
        seen: dict[str, None] = {}
        for account in requested:
            seen.setdefault(extract_email_address(account), None)
        return list(seen)
    known = set(client_handler.get_clients().keys()) | set(
        nostr_handler.get_all_adapters().keys()
    )
    return sorted(known)


@router.post("/search-all")
async def search_all(request: SearchAllRequest) -> Response[dict]:
    """Search every account across every transport in one call.

    IMAP accounts are queried server-side with ``SearchCriteria``; Nostr
    accounts are filtered against their local mailbox records.  A failing
    account (offline IMAP, no adapter) is skipped so one dead account
    never breaks the global search.  Results are newest-first and capped
    at ``limit`` (max 200).
    """
    try:
        limit = max(1, min(request.limit, SEARCH_ALL_MAX_RESULTS))

        criteria: SearchCriteria | str = ""
        if request.criteria:
            criteria = SearchCriteria(**request.criteria)
        if request.query:
            if isinstance(criteria, SearchCriteria) and not criteria.include:
                criteria.include = request.query
            elif not isinstance(criteria, SearchCriteria):
                criteria = SearchCriteria(include=request.query)

        accounts = _search_all_accounts(request.accounts)
        results: list[dict] = []
        searched: list[str] = []

        for account in accounts:
            # --- IMAP side ------------------------------------------
            if client_handler.is_client_exists(account):
                try:
                    connection = check_openmail_connection_availability(account)
                    if isinstance(connection, Response):
                        uvicorn_logger.error(connection.message)
                    else:
                        client = client_handler.get_client(account)
                        client.imap.search_emails(request.folder, criteria)
                        mailbox = client.imap.get_emails(1, limit)
                        for email in mailbox.emails:
                            email.route = _email_route(email.source, email.sender)
                            entry = {key: email[key] for key in email.keys()}
                            entry["account"] = account
                            results.append(entry)
                        searched.append(account)
                except Exception as e:
                    uvicorn_logger.error(
                        "search-all IMAP stage failed for %s: %s", account, e
                    )

            # --- Nostr side -----------------------------------------
            adapter = nostr_handler.get_adapter(account)
            if adapter is not None:
                try:
                    for record in adapter.fetch_records(
                        limit=NOSTR_RECORD_PAGE_LIMIT
                    ):
                        if isinstance(criteria, SearchCriteria) and not (
                            _nostr_record_matches(record, criteria)
                        ):
                            continue
                        email = _nostr_record_to_email(record)
                        entry = {key: email[key] for key in email.keys()}
                        entry["account"] = account
                        results.append(entry)
                    if account not in searched:
                        searched.append(account)
                except Exception as e:
                    uvicorn_logger.error(
                        "search-all Nostr stage failed for %s: %s", account, e
                    )

        results.sort(key=lambda item: _email_timestamp(item.get("date")), reverse=True)
        results = results[:limit]

        return Response(
            success=True,
            message="Search across accounts completed.",
            data={
                "results": results,
                "total": len(results),
                "accounts": searched,
            },
        )
    except Exception as e:
        return Response(
            success=False,
            message=err_msg("There was an error while searching across accounts.", str(e)),
        )


@router.get("/get-mailbox/{account}")
async def get_mailbox(
    account: str,
    folder: Optional[str] = None,
    search: Optional[str] = None,
    offset_start: Optional[int] = None,
    offset_end: Optional[int] = None,
) -> Response[OpenmailTaskResults[Mailbox]]:
    """Fetch a mailbox, merging every transport the account has.

    An account may hold IMAP mail, Nostr mail, or both.  Previously the
    Nostr branch returned early, so an account with a Nostr identity
    never saw its IMAP mail.  Both sides are now fetched, tagged with
    their delivery route, and sorted newest-first.
    """
    try:
        account = extract_email_address(account)
        started_at = time.perf_counter()

        adapter = (
            nostr_handler.get_adapter(account)
            if nostr_handler.has_adapter(account)
            else None
        )
        has_imap = client_handler.is_client_exists(account)

        if adapter is None and not has_imap:
            return Response(
                success=False,
                message=f"No mail transport available for {account}.",
            )

        # --- IMAP side (optional) ------------------------------------
        imap_mailbox: Optional[Mailbox] = None
        if has_imap:
            imap_started = time.perf_counter()
            connection = check_openmail_connection_availability(account)
            if isinstance(connection, Response):
                if adapter is None:
                    return connection
                # IMAP is down but Nostr still works: degrade, don't fail.
                uvicorn_logger.error(connection.message)
            else:
                search_criteria = _parse_search_criteria(search)
                client_handler.get_client(account).imap.search_emails(
                    folder, search_criteria
                )
                imap_mailbox = client_handler.get_client(account).imap.get_emails(
                    offset_start, offset_end
                )
                uvicorn_logger.debug(
                    "get-mailbox IMAP stage took %.0f ms for %s",
                    (time.perf_counter() - imap_started) * 1000,
                    account,
                )

        # --- Nostr side (optional) -----------------------------------
        nostr_emails: list[Email] = []
        if adapter is not None:
            criteria = _parse_search_criteria(search)
            for record in adapter.fetch_records(limit=NOSTR_RECORD_PAGE_LIMIT):
                if isinstance(criteria, SearchCriteria) and not _nostr_record_matches(
                    record, criteria
                ):
                    continue
                nostr_emails.append(_nostr_record_to_email(record))

        # --- Merge: tag routes, sort newest first --------------------
        emails: list[Email] = []
        if imap_mailbox is not None:
            for email in imap_mailbox.emails:
                email.route = _email_route(email.source, email.sender)
                emails.append(email)
        emails.extend(nostr_emails)
        emails.sort(key=lambda e: _email_timestamp(e.date), reverse=True)

        total = (imap_mailbox.total if imap_mailbox is not None else 0) + len(
            nostr_emails
        )
        mailbox_folder = (
            imap_mailbox.folder
            if imap_mailbox is not None
            else (folder or "nostr")
        )

        if imap_mailbox is not None and nostr_emails:
            message = "Unified mailbox (IMAP + Nostr) fetched successfully."
        elif imap_mailbox is not None:
            message = "Emails fetched successfully."
        else:
            message = "Nostr mailbox fetched successfully."

        uvicorn_logger.debug(
            "get-mailbox total took %.0f ms for %s (%d emails)",
            (time.perf_counter() - started_at) * 1000,
            account,
            len(emails),
        )

        return Response(
            success=True,
            message=message,
            data={
                account: Mailbox(
                    total=total,
                    emails=emails,
                    folder=mailbox_folder,
                )
            },
        )
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while fetching emails.", str(e)))


@router.get("/paginate-mailbox/{account}/{offset_start}/{offset_end}")
async def paginate_mailbox(
    account: str,
    offset_start: int,
    offset_end: int
) -> Response[OpenmailTaskResults[Mailbox]]:
    try:
        account = extract_email_address(account)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        return Response(
            success=True,
            message="Emails paginated successfully.",
            data={account: client_handler.get_client(account).imap.get_emails(offset_start, offset_end)}
        )
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while paginating emails.", str(e)))

@router.get("/get-folders/{account}")
async def get_folders(
    account: str,
) -> Response[OpenmailTaskResults[list[str]]]:
    try:
        account = extract_email_address(account)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        return Response(
            success=True,
            message="Folders fetched successfully.",
            data={account: client_handler.get_client(account).imap.get_folders(tagged=True)}
        )
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while fetching folders.", str(e)))

@router.get("/get-email-content/{account}/{folder}/{uid}")
def get_email_content(
    account: str,
    folder: str,
    uid: str
) -> Response[Email]:
    try:
        account = extract_email_address(account)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        return Response(
            success=True,
            message="Email content fetched successfully.",
            data=client_handler.get_client(account).imap.get_email_content(unquote(folder), uid)
        )
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while fetching email content.", str(e)))

@router.get("/download-attachment/{account}/{folder}/{uid}/{name}")
def download_attachment(
    account: str,
    folder: str,
    uid: str,
    name: str,
    cid: str = ""
) -> Response[Attachment]:
    try:
        account = extract_email_address(account)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        return Response[Attachment](
            success=True,
            message="Email content fetched successfully.",
            data=client_handler.get_client(account).imap.download_attachment(
                unquote(folder),
                uid,
                name,
                cid
            ),
        )
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while fetching email content.", str(e)))

async def convert_uploadfile_to_attachment(attachments: list[UploadFile]) -> list[Attachment]:
    converted_to_attachment_list = []
    if not attachments:
        return []

    for attachment in attachments:
        data = await attachment.read()
        if data:
            converted_to_attachment_list.append(
                Attachment(
                    name=attachment.filename,
                    data=data,
                    type=attachment.content_type,
                    size=len(data),
                )
            )
    return converted_to_attachment_list

class SendEmailFormData(BaseModel):
    sender: str # Name Surname <namesurname@domain.com> or namesurname@domain.com
    receivers: str  # mail addresses separated by comma
    subject: str
    body: str
    uid: Optional[str] = None
    cc: Optional[str] = None # mail addresses separated by comma
    bcc: Optional[str] = None # mail addresses separated by comma
    attachments: list[UploadFile] = []
    # Where to deliver: "auto" (smart per-recipient routing), "email"
    # (SMTP only) or "nostr" (Nostr relays only).
    transport: str = "auto"


def _recipient_address(value: str) -> str:
    """Strip a display name, leaving the bare address (email or npub)."""
    if "<" in value and ">" in value:
        return value.split("<", 1)[1].split(">", 1)[0].strip()
    return value.strip()


def _is_npub(value: str) -> bool:
    """True for a bech32 npub or a raw 64-char hex public key."""
    value = value.strip()
    if value.startswith("npub1"):
        return True
    return len(value) == 64 and all(
        char in "0123456789abcdefABCDEF" for char in value
    )


def _split_receivers(receivers: str) -> tuple[list[str], list[str]]:
    """Split a comma-separated receiver list into (npubs, emails)."""
    npub_recipients: list[str] = []
    email_recipients: list[str] = []
    for raw in receivers.split(","):
        if not raw.strip():
            continue
        if _is_npub(_recipient_address(raw)):
            npub_recipients.append(_recipient_address(raw))
        else:
            email_recipients.append(raw.strip())
    return npub_recipients, email_recipients


@router.post("/send-email")
async def send_email(
    form_data: Annotated[SendEmailFormData, Form()],
) -> Response:
    """
    Send a message with transport selection:

    - ``auto``: smart per-recipient routing — npub recipients go out over
      Nostr relays (when this account has an identity), everything else
      goes out over SMTP. Having a Nostr identity never hijacks plain
      email sends anymore.
    - ``email`` / ``nostr``: force a single transport.
    """
    try:
        account = extract_email_address(form_data.sender)
        transport = (form_data.transport or "auto").lower()
        if transport not in ("auto", "email", "nostr"):
            transport = "auto"

        npub_recipients, email_recipients = _split_receivers(form_data.receivers)
        if not npub_recipients and not email_recipients:
            return Response(success=False, message="No recipients provided.")
        if transport == "email" and npub_recipients:
            return Response(
                success=False,
                message="npub recipients can only be reached over Nostr — use Smart or Nostr routing.",
            )
        if transport == "nostr" and email_recipients:
            return Response(
                success=False,
                message="Email recipients can only be reached over SMTP — use Smart or Email routing.",
            )

        legs: list[str] = []
        ok_all = True

        send_over_nostr = transport in ("auto", "nostr") and bool(npub_recipients)
        send_over_smtp = transport in ("auto", "email") and bool(email_recipients)

        if send_over_nostr:
            if not nostr_handler.has_adapter(account):
                ok_all = False
                legs.append("Nostr: no identity is registered for this account.")
            else:
                adapter = nostr_handler.get_adapter(account)
                from src.mail_abstraction.base import Address
                from_addr = Address(address=adapter.identity.public_key_hex)
                to_addrs = []
                for recip in npub_recipients:
                    if recip.startswith("npub1"):
                        from src.nostr.identity import npub_decode
                        raw = npub_decode(recip)
                        to_addrs.append(Address(address=raw.hex()))
                    else:
                        to_addrs.append(Address(address=recip))
                ok, msg = adapter.send_message(
                    from_address=from_addr,
                    to_addresses=to_addrs,
                    subject=form_data.subject,
                    body=form_data.body,
                )
                ok_all = ok_all and ok
                legs.append(f"Nostr: {msg}")

        if send_over_smtp:
            response = check_openmail_connection_availability(account)
            if isinstance(response, Response):
                ok_all = False
                legs.append(f"SMTP: {response.message}")
            else:
                status, msg = client_handler.get_client(account).smtp.send_email(
                    Draft(
                        sender=form_data.sender,
                        receivers=", ".join(email_recipients),
                        subject=form_data.subject,
                        body=form_data.body,
                        cc=form_data.cc,
                        bcc=form_data.bcc,
                        attachments=await convert_uploadfile_to_attachment(
                            form_data.attachments
                        ),
                    )
                )
                ok_all = ok_all and status
                legs.append(f"SMTP: {msg}")

        return Response(
            success=ok_all,
            message=" | ".join(legs) if legs else "Nothing was sent.",
        )
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while sending email.", str(e)))


@router.post("/reply-email/{original_message_id}")
async def reply_email(
    original_message_id: str,
    form_data: Annotated[SendEmailFormData, Form()]
) -> Response:
    try:
        account = extract_email_address(form_data.sender)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        status, msg = client_handler.get_client(account).smtp.reply_email(
            original_message_id,
            Draft(
                sender=form_data.sender,
                receivers=form_data.receivers,
                subject=form_data.subject,
                body=form_data.body,
                cc=form_data.cc,
                bcc=form_data.bcc,
                attachments=await convert_uploadfile_to_attachment(form_data.attachments),
            )
        )

        return Response(success=status, message=msg)
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while replying email.", str(e)))


@router.post("/forward-email/{original_message_id}")
async def forward_email(
    original_message_id: str,
    form_data: Annotated[SendEmailFormData, Form()]
) -> Response:
    try:
        account = extract_email_address(form_data.sender)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        status, msg = client_handler.get_client(account).smtp.forward_email(
            original_message_id,
            Draft(
                sender=form_data.sender,
                receivers=form_data.receivers,
                subject=form_data.subject,
                body=form_data.body,
                cc=form_data.cc,
                bcc=form_data.bcc,
                attachments=await convert_uploadfile_to_attachment(form_data.attachments),
            )
        )

        return Response(success=status, message=msg)
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while forwarding email.", str(e)))

@router.post("/save-email-as-draft")
async def save_email_as_draft(
    form_data: Annotated[SendEmailFormData, Form()],
    appenduid: str | None = None
) -> Response:
    try:
        account = extract_email_address(form_data.sender)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        appenduid = client_handler.get_client(account).imap.save_email_as_draft(
            client_handler.get_client(account).smtp.create_email(Draft(
                sender=form_data.sender,
                receivers=form_data.receivers,
                subject=form_data.subject,
                body=form_data.body,
                cc=form_data.cc,
                bcc=form_data.bcc,
                attachments=await convert_uploadfile_to_attachment(form_data.attachments),
            )),
            appenduid
        )

        return Response(success=True, message="Email saved as draft successfully.", data={appenduid: appenduid})
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while saving email as draft.", str(e)))

class MarkEmailRequest(BaseModel):
    account: str
    sequence_set: str
    mark: str
    folder: str = Folder.Inbox


@router.post("/mark-email")
async def mark_email(request_body: MarkEmailRequest) -> Response:
    try:
        account = extract_email_address(request_body.account)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        status, msg = client_handler.get_client(account).imap.mark_email(
            request_body.sequence_set,
            request_body.mark,
            request_body.folder,
        )
        return Response(success=status, message=msg)
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while marking email.", str(e)))


class UnmarkEmailRequest(BaseModel):
    account: str
    sequence_set: str
    mark: str
    folder: str = Folder.Inbox


@router.post("/unmark-email")
async def unmark_email(request_body: UnmarkEmailRequest) -> Response:
    try:
        account = extract_email_address(request_body.account)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        status, msg = client_handler.get_client(account).imap.unmark_email(
            request_body.sequence_set,
            request_body.mark,
            request_body.folder,
        )
        return Response(success=status, message=msg)
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while unmarking email.", str(e)))


class MoveEmailRequest(BaseModel):
    account: str
    source_folder: str
    destination_folder: str
    sequence_set: str


@router.post("/move-email")
async def move_email(request_body: MoveEmailRequest) -> Response:
    try:
        account = extract_email_address(request_body.account)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        status, msg = client_handler.get_client(account).imap.move_email(
            request_body.source_folder,
            request_body.destination_folder,
            request_body.sequence_set,
        )
        return Response(success=status, message=msg)
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while moving email.", str(e)))


class CopyEmailRequest(BaseModel):
    account: str
    source_folder: str
    destination_folder: str
    sequence_set: str


@router.post("/copy-email")
async def copy_email(request_body: CopyEmailRequest) -> Response:
    try:
        account = extract_email_address(request_body.account)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        status, msg = client_handler.get_client(account).imap.copy_email(
            request_body.source_folder,
            request_body.destination_folder,
            request_body.sequence_set,
        )
        return Response(success=status, message=msg)
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while copying email.", str(e)))


class DeleteEmailRequest(BaseModel):
    account: str
    folder: str
    sequence_set: str


@router.post("/delete-email")
async def delete_email(request_body: DeleteEmailRequest) -> Response:
    try:
        account = extract_email_address(request_body.account)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        status, msg = client_handler.get_client(account).imap.delete_email(
            request_body.folder,
            request_body.sequence_set
        )
        return Response(success=status, message=msg)
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while deleting email.", str(e)))


class CreateFolderRequest(BaseModel):
    account: str
    folder_name: str
    parent_folder: str | None = None


@router.post("/create-folder")
async def create_folder(request_body: CreateFolderRequest) -> Response:
    try:
        account = extract_email_address(request_body.account)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        status, msg = client_handler.get_client(account).imap.create_folder(
            request_body.folder_name, request_body.parent_folder
        )
        return Response(success=status, message=msg)
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while creating folder.", str(e)))


class RenameFolderRequest(BaseModel):
    account: str
    folder_name: str
    new_folder_name: str


@router.post("/rename-folder")
async def rename_folder(request_body: RenameFolderRequest) -> Response:
    try:
        account = extract_email_address(request_body.account)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        status, msg = client_handler.get_client(account).imap.rename_folder(
            request_body.folder_name, request_body.new_folder_name
        )
        return Response(success=status, message=msg)
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while renaming folder.", str(e)))


class MoveFolderRequest(BaseModel):
    account: str
    folder_name: str
    destination_folder: str


@router.post("/move-folder")
async def move_folder(request_body: MoveFolderRequest) -> Response:
    try:
        account = extract_email_address(request_body.account)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        status, msg = client_handler.get_client(account).imap.move_folder(
            request_body.folder_name, request_body.destination_folder
        )
        return Response(success=status, message=msg)
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while moving folder.", str(e)))


class DeleteFolderRequest(BaseModel):
    account: str
    folder_name: str
    delete_subfolders: bool

@router.post("/delete-folder")
async def delete_folder(request_body: DeleteFolderRequest) -> Response:
    try:
        account = extract_email_address(request_body.account)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        status, msg = client_handler.get_client(account).imap.delete_folder(
            request_body.folder_name,
            request_body.delete_subfolders
        )
        return Response(success=status, message=msg)
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while deleting folder.", str(e)))

class UnsubscribeEmailRequest(BaseModel):
    account: str
    list_unsubscribe: str
    list_unsubscribe_post: str | None = None

@router.post("/unsubscribe-email")
async def unsubscribe_email(request_body: UnsubscribeEmailRequest) -> Response:
    try:
        account = extract_email_address(request_body.account)
        response = check_openmail_connection_availability(account)
        if isinstance(response, Response):
            return response

        status, msg = client_handler.get_client(account).smtp.unsubscribe(
            request_body.account,
            request_body.list_unsubscribe,
            request_body.list_unsubscribe_post
        )
        return Response(success=status, message=msg)
    except Exception as e:
        return Response(success=False, message=err_msg("There was an error while unsubscribing.", str(e)))

__all__ = ["router"]

"""
Execute openmail tasks with threading module:

def execute_openmail_task_concurrently(
    accounts: set[str], # unique email addresses
    func: Callable[...],
    **params
) -> OpenmailTaskResults:
    result: OpenmailTaskResults = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_TASK_WORKER) as executor:
        future_to_emails = {
            executor.submit(func, client, **params): email_address
            for email_address, client in openmail_clients.items()
            if email_address in accounts
        }

        for future in concurrent.futures.as_completed(future_to_emails, IMAP_OPERATION_TIMEOUT):
            email_address = future_to_emails[future]
            future = future.result()
            result[email_address] = future
            print(f"Result for {email_address}: {future}") # TODO: Comment this

        return result

# Usage examples of `execute_openmail_task_concurrently`:
# instance.imap.get_folders()
execute_openmail_task_concurrently(
    unique_email_addresses,
    lambda client, **params: client.imap.get_folders(),
)
# instance.imap.search_emails()
execute_openmail_task_concurrently(
    unique_email_addresses,
    lambda client, **params: client.imap.search_emails(**params),
    folder=folder,
    search=SearchCriteria.parse_raw(search) if search else None,
)
# instance.imap.get_emails()
execute_openmail_task_concurrently(
    unique_email_addresses,
    lambda client, **params: client.imap.get_emails(**params),
    offset_start=offset_start,
    offset_end=offset_end,
)
"""
