# Plan: Connect Nostr Transport to Mail System

## Context

The Narada codebase has two parallel mail systems that need to be connected:

1. **Existing**: IMAP/SMTP via Openmail — `ClientHandler` manages `Openmail` instances, routers call `client.imap.*` / `client.smtp.*` directly
2. **New**: Nostr transport — `NostrAdapter` is fully implemented and tested (79 tests), but has zero integration with the server or client

The goal is to wire `NostrAdapter` into the server so the app can send/receive encrypted email via Nostr relays, alongside (or instead of) IMAP/SMTP.

## Architecture

```
Client (SvelteKit/Tauri)
  → HTTP API → FastAPI Server
    → ClientHandler (IMAP/SMTP)     ← existing
    → NostrHandler (Nostr relays)   ← new
    → NostrAdapter instances per account
      → RelayPool → Nostr Relays
```

## Implementation Plan

### Phase 1: Server-side NostrHandler (no client changes yet)

**Goal**: Create a singleton to manage NostrAdapter instances, mirroring ClientHandler's pattern.

#### 1.1 Create `src/internal/nostr_handler.py`
- Singleton `NostrHandler` class
- `nostr_adapters: dict[str, NostrAdapter]` — keyed by account_id (npub or email)
- `create_nostr_adapters(accounts)` — iterate accounts, create NostrAdapter for each
- `get_adapter(account) -> NostrAdapter`
- `add_adapter(account_id, adapter)`
- `remove_adapter(account_id)`
- `shutdown()` — disconnect all adapters
- Load Nostr identity from client-side localStorage (sent during registration) or generate server-side

#### 1.2 Create `src/routers/nostr_tasks.py`
New router with Nostr-specific endpoints:

| Endpoint | Method | Purpose |
|---|---|---|
| `/nostr/register-identity` | POST | Register a Nostr identity (npub + encrypted nsec) for an account |
| `/nostr/get-identity/{account}` | GET | Get the Nostr public key (npub) for an account |
| `/nostr/send-email` | POST | Send an email via Nostr relays (kind 1050 event) |
| `/nostr/get-mailbox/{account}` | GET | Fetch received Nostr messages from local JSONL |
| `/nostr/subscribe/{account}` | WS | WebSocket subscription for incoming Nostr events |
| `/nostr/get-relays` | GET | List configured Nostr relays and their connection status |
| `/nostr/status/{account}` | GET | Connection status for a Nostr account |

#### 1.3 Update `src/main.py`
- Import `NostrHandler` in lifespan
- Call `nostr_handler.create_nostr_adapters(accounts)` during startup
- Include `nostr_tasks` router
- Call `nostr_handler.shutdown()` on shutdown

### Phase 2: Wire Nostr into existing routers (dual-dispatch)

**Goal**: Existing mailbox endpoints should work with both IMAP and Nostr accounts.

#### 2.1 Update `src/internal/client_handler.py`
- Add a method `is_nostr_account(account) -> bool` (checks if NostrHandler has an adapter for this account)
- No changes to existing IMAP logic — it continues to work as-is

#### 2.2 Update `src/routers/mailbox_tasks.py`
- In `get_mailbox`, `get_email_content`, `send_email`: check if account is Nostr
- If Nostr → delegate to `NostrHandler.get_adapter(account).fetch_messages()` / `.send_message()`
- If IMAP → continue with existing `client_handler.get_client(account).imap.*` / `.smtp.*` logic

#### 2.3 Update `src/routers/account_tasks.py`
- `add-account`: Support Nostr accounts (skip IMAP connection if Nostr identity is provided)
- `get-accounts`: Include Nostr accounts in the connected/failed lists

### Phase 3: Client-side integration

**Goal**: Connect the existing SvelteKit client to the new Nostr endpoints.

#### 3.1 Update `client/src/lib/services/NostrIdentityService.ts`
- Add `registerIdentity(accountId, npub, encryptedNsec)` — POST to `/nostr/register-identity`
- Add `getIdentity(accountId)` — GET from `/nostr/get-identity/{account}`

#### 3.2 Update registration flow
- In `GenerateIdentity.svelte`: after generating identity, call `/nostr/register-identity`
- In `RecoverIdentity.svelte`: after recovering identity, call `/nostr/register-identity`
- The Nostr adapter will use the registered identity for signing/verifying events

#### 3.3 Update mail controller
- In `MailboxController.getMailbox()`: check account source type
- If Nostr → call `/nostr/get-mailbox/{account}` instead of `/get-mailbox/{account}`
- If Nostr → call `/nostr/send-email` instead of `/send-email`

### Phase 4: Add Nostr-specific routes to Menu

**Goal**: Show Nostr delivery status in the sidebar.

#### 4.1 Update `Menu.svelte`
- Show relay connection status in the peer pill (e.g., "3 relays connected" instead of "node offline")
- Route badges already display correctly (direct/relay/gateway) based on message source

#### 4.2 Update `Network.svelte`
- Show actual Nostr relay connections instead of account-based peer list
- Display relay URLs, connection status, latency

### Phase 5: Add Nostr-specific send flow

**Goal**: When sending an email to a Nostr recipient, use Nostr transport.

#### 5.1 Update `Compose.svelte`
- Detect if recipient address is a Nostr pubkey (npub or hex)
- If Nostr → use `/nostr/send-email` endpoint
- If email → use existing `/send-email` endpoint

## Files to Create
- `node/src/internal/nostr_handler.py`
- `node/src/routers/nostr_tasks.py`

## Files to Modify
- `node/src/main.py` — add NostrHandler to lifespan + include router
- `node/src/routers/account_tasks.py` — support Nostr account registration
- `node/src/routers/mailbox_tasks.py` — dual-dispatch for Nostr accounts
- `client/src/lib/services/NostrIdentityService.ts` — add server registration
- `client/src/lib/ui/Landing/Register/GenerateIdentity.svelte` — register identity on server
- `client/src/lib/ui/Landing/Register/RecoverIdentity.svelte` — register identity on server
- `client/src/lib/ui/Layout/Main/Content/Compose.svelte` — Nostr send detection

## Verification
1. Run `cd node && uv run pytest` — all 79 Nostr tests + 9 mail_abstraction tests should pass
2. Run `cd client && bun run check` — TypeScript types should be clean
3. Manual test: start server, register a Nostr identity, send a message to another Nostr identity, verify it appears in the recipient's mailbox
