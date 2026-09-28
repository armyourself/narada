import { showToast } from "@/lib/stores/ui";

/**
 * Live inbox feed: one WebSocket per app to the backend's
 * `GET /nostr/subscribe/{account}` endpoint.
 *
 * The backend pushes one JSON frame per persisted Nostr event and a
 * `{ type: "ping" }` keepalive every 30s.  This module owns the socket
 * lifecycle (including reconnect with capped backoff) and fans messages
 * out to subscribers, so components only subscribe/unsubscribe.
 */

export interface NostrLiveMessage {
    uid: string;
    sender: string;
    subject: string;
    preview?: string | null;
    date?: string;
    type?: string;
}

type Listener = (message: NostrLiveMessage) => void;

const listeners = new Set<Listener>();
const seenUids = new Set<string>();
const SEEN_LIMIT = 500;

let socket: WebSocket | null = null;
let socketKey = "";
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let attempt = 0;
let stopped = false;

function toWsUrl(server: string, account: string): string {
    return (
        server.replace(/^http/, "ws") +
        `/nostr/subscribe/${encodeURIComponent(account)}`
    );
}

function notify(message: NostrLiveMessage): void {
    if (message.uid && seenUids.has(message.uid)) return;
    if (message.uid) {
        seenUids.add(message.uid);
        if (seenUids.size > SEEN_LIMIT) {
            const oldest = seenUids.values().next();
            if (!oldest.done) seenUids.delete(oldest.value);
        }
    }
    for (const listener of listeners) {
        try {
            listener(message);
        } catch (error) {
            console.error("Nostr live listener failed", error);
        }
    }
}

function scheduleReconnect(server: string, account: string): void {
    if (stopped || retryTimer) return;
    const delay = Math.min(1000 * 2 ** attempt, 30_000);
    attempt += 1;
    retryTimer = setTimeout(() => {
        retryTimer = null;
        open(server, account);
    }, delay);
}

function open(server: string, account: string): void {
    const key = toWsUrl(server, account);
    if (socket && socketKey === key) return; // already live for this pair
    if (socket) {
        socket.close();
        socket = null;
    }
    stopped = false;
    socketKey = key;

    let ws: WebSocket;
    try {
        ws = new WebSocket(key);
    } catch (error) {
        console.error("Nostr live socket could not be created", error);
        scheduleReconnect(server, account);
        return;
    }
    socket = ws;

    ws.addEventListener("open", () => {
        attempt = 0;
    });
    ws.addEventListener("message", (event) => {
        let payload: NostrLiveMessage | null = null;
        try {
            payload = JSON.parse(String(event.data)) as NostrLiveMessage;
        } catch {
            return;
        }
        if (!payload || payload.type === "ping") return;
        notify(payload);
        showToast({
            content: `New Nostr mail: ${payload.subject || payload.sender || "message"}`,
        });
    });
    ws.addEventListener("close", (event) => {
        if (socket === ws) socket = null;
        // The backend closes immediately when the account has no Nostr
        // identity — retrying would spin forever until one is created.
        if (event.reason?.includes("No Nostr adapter")) {
            stopped = true;
            return;
        }
        scheduleReconnect(server, account);
    });
    ws.addEventListener("error", () => {
        ws.close();
    });
}

/** Open (or re-target) the live feed for *account*. Idempotent. */
export function startNostrLive(server: string, account: string): void {
    if (!server || !account) return;
    if (socketKey === toWsUrl(server, account) && socket) return;
    open(server, account);
}

/** Drop the feed (used on account switch / teardown). */
export function stopNostrLive(): void {
    stopped = true;
    if (retryTimer) {
        clearTimeout(retryTimer);
        retryTimer = null;
    }
    const ws = socket;
    socket = null;
    socketKey = "";
    attempt = 0;
    ws?.close();
}

/** Register a listener; returns an unsubscribe function. */
export function subscribeNostrLive(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}
