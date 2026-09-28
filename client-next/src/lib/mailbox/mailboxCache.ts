import type { Mailbox } from "@/lib/types";

// Stale-while-revalidate cache for mailbox reads.
//
// Switching folders or accounts paints the last known list instantly,
// then the in-flight `/get-mailbox` request revalidates it. Entries are
// keyed by account + folder + search criteria, so a search result never
// leaks into the plain folder view.
const CACHE_TTL_MS = 30_000;
const CACHE_MAX_ENTRIES = 32;

interface CacheEntry {
    mailbox: Mailbox;
    storedAt: number;
}

const cache = new Map<string, CacheEntry>();

export function mailboxCacheKey(
    account: string,
    folder: string | undefined,
    search: string,
): string {
    return `${account}|${folder ?? ""}|${search}`;
}

export function readMailboxCache(key: string): Mailbox | null {
    const entry = cache.get(key);
    if (!entry) return null;
    // Recency: refresh insertion order for the LRU cap below.
    cache.delete(key);
    cache.set(key, entry);
    return entry.mailbox;
}

export function isMailboxCacheFresh(key: string): boolean {
    const entry = cache.get(key);
    return entry !== undefined && Date.now() - entry.storedAt < CACHE_TTL_MS;
}

export function writeMailboxCache(key: string, mailbox: Mailbox): void {
    cache.delete(key);
    cache.set(key, { mailbox, storedAt: Date.now() });
    while (cache.size > CACHE_MAX_ENTRIES) {
        const oldest = cache.keys().next().value;
        if (oldest === undefined) break;
        cache.delete(oldest);
    }
}

export function clearMailboxCache(account?: string): void {
    if (!account) {
        cache.clear();
        return;
    }
    for (const key of [...cache.keys()]) {
        if (key.startsWith(`${account}|`)) cache.delete(key);
    }
}
