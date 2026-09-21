<script module lang="ts">
    import { SharedStore } from "$lib/stores/shared.svelte";
    import { type Mailbox, Folder } from "$lib/types";
    import {
        PAGINATE_MAILBOX_CHECK_DELAY_MS,
        WAIT_FOR_EMAILS_TIMEOUT_MS,
    } from "$lib/constants";
    import { MailboxController } from "$lib/mailbox";
    import { PreferenceStore } from "$lib/preferences";
    import { getContext, setContext } from "svelte";

    let currentMailbox = $derived.by(() => {
        if (SharedStore.currentAccount === "home") {
            let currentMailbox: Mailbox = {
                total: 0,
                emails: { prev: [], current: [], next: [] },
                folder: Folder.Inbox,
            };
            Object.values(SharedStore.mailboxes).forEach((mailbox) => {
                currentMailbox.total += mailbox.total;
                currentMailbox.emails.prev.push(...mailbox.emails.prev);
                currentMailbox.emails.current.push(...mailbox.emails.current);
                currentMailbox.emails.next.push(...mailbox.emails.next);
            });
            Object.values(currentMailbox.emails).forEach((emails) => {
                emails.sort(
                    (a, b) =>
                        new Date(b.date).getTime() - new Date(a.date).getTime(),
                );
            });
            return currentMailbox;
        } else {
            return SharedStore.mailboxes[
                SharedStore.currentAccount.email_address
            ];
        }
    });

    export function getCurrentMailbox() {
        return currentMailbox;
    }

    export type EmailSelection = "1:*" | string[];
    export type GroupedUidSelection = [email_address: string, uids: string][];
    export type GroupedMessageIdSelection = [email_address: string, message_ids: string[]][];

    export const CONTEXT_KEY = "MAILBOX";
    export interface MailboxContext {
        currentOffset: { value: number };
        emailSelection: { value: EmailSelection };
        getGroupedUidSelection: () => GroupedUidSelection;
    }

    export function getMailboxContext(): MailboxContext {
        return getContext(CONTEXT_KEY);
    }

    let currentOffset: { value: number } = $state({ value: 1 });
    let emailSelection: { value: EmailSelection } = $state({ value: [] });
    let groupedUidSelection: GroupedUidSelection = $derived.by(() => {
        if (!emailSelection) return [];
        const accountUidMap: Record<string, string> = {};
        if (emailSelection.value === "1:*") {
            if (SharedStore.currentAccount === "home") {
                SharedStore.accounts.forEach((account) => {
                    accountUidMap[account.email_address] = "1:*";
                });
            } else {
                accountUidMap[SharedStore.currentAccount.email_address] = "1:*";
            }
        } else {
            emailSelection.value.forEach((selection) => {
                const [emailAddr, uid] = selection.split(",");
                accountUidMap[emailAddr] = Object.hasOwn(accountUidMap, emailAddr)
                    ? accountUidMap[emailAddr] + "," + uid
                    : uid;
            });
        }
        return Object.entries(accountUidMap);
    });

    let waitPrev: ReturnType<typeof setInterval> | null;

    export async function paginateMailboxBackward(
        currentOffset: number,
    ): Promise<void> {
        const MAILBOX_LENGTH = Number(PreferenceStore.mailboxLength);
        if (currentOffset <= MAILBOX_LENGTH) return;

        return new Promise((resolve) => {
            if (!waitPrev) {
                const emailAddrs =
                    SharedStore.currentAccount !== "home"
                        ? [SharedStore.currentAccount.email_address]
                        : SharedStore.accounts.map((acc) => acc.email_address);

                const shiftEmailPagesBackward = () => {
                    currentMailbox.emails.next = currentMailbox.emails.current;
                    currentMailbox.emails.current = currentMailbox.emails.prev;
                    currentMailbox.emails.prev = [];

                    const prevOffsetStart = Math.max(1, currentOffset - MAILBOX_LENGTH * 2);
                    const prevOffsetEnd = Math.max(MAILBOX_LENGTH, currentOffset - 1 - MAILBOX_LENGTH);

                    if (prevOffsetEnd < currentOffset) {
                        emailAddrs.forEach((emailAddr) => {
                            MailboxController.paginateEmails(
                                SharedStore.accounts.find((acc) => acc.email_address === emailAddr)!,
                                prevOffsetStart,
                                prevOffsetEnd,
                            );
                        });
                    }
                };

                const clearWaitPrevInterval = () => {
                    if (waitPrev) { clearInterval(waitPrev); waitPrev = null; }
                };

                if (currentMailbox.emails.prev.length > 0) {
                    shiftEmailPagesBackward();
                    clearWaitPrevInterval();
                    resolve();
                } else {
                    const startTime = Date.now();
                    waitPrev = setInterval(() => {
                        if (Date.now() - startTime >= WAIT_FOR_EMAILS_TIMEOUT_MS) {
                            clearWaitPrevInterval();
                            resolve();
                        }
                        if (currentMailbox.emails.prev.length > 0) {
                            shiftEmailPagesBackward();
                            clearWaitPrevInterval();
                            resolve();
                        }
                    }, PAGINATE_MAILBOX_CHECK_DELAY_MS);
                }
            }
        });
    }

    let waitNext: ReturnType<typeof setInterval> | null;

    export async function paginateMailboxForward(
        currentOffset: number,
    ): Promise<void> {
        if (currentOffset >= currentMailbox.total) return;

        return new Promise((resolve) => {
            if (!waitNext) {
                const MAILBOX_LENGTH = Number(PreferenceStore.mailboxLength);
                const emailAddrs =
                    SharedStore.currentAccount !== "home"
                        ? [SharedStore.currentAccount.email_address]
                        : SharedStore.accounts.filter((acc) => {
                              return SharedStore.mailboxes[acc.email_address].total > currentOffset;
                          });

                const shiftEmailPagesForward = () => {
                    currentMailbox.emails.prev = currentMailbox.emails.current;
                    currentMailbox.emails.current = currentMailbox.emails.next;
                    currentMailbox.emails.next = [];

                    const nextOffsetStart = Math.min(currentMailbox.total, Math.max(1, currentOffset + MAILBOX_LENGTH * 2));
                    const nextOffsetEnd = Math.min(currentMailbox.total, Math.max(1, nextOffsetStart - 1 + MAILBOX_LENGTH));

                    if (nextOffsetStart <= currentMailbox.total) {
                        emailAddrs.forEach((emailAddr) => {
                            MailboxController.paginateEmails(
                                SharedStore.accounts.find((acc) => acc.email_address === emailAddr)!,
                                nextOffsetStart,
                                nextOffsetEnd,
                            );
                        });
                    }
                };

                const clearWaitNextInterval = () => {
                    if (waitNext) { clearInterval(waitNext); waitNext = null; }
                };

                if (currentMailbox.emails.next.length > 0) {
                    shiftEmailPagesForward();
                    clearWaitNextInterval();
                    resolve();
                } else {
                    const startTime = Date.now();
                    waitNext = setInterval(() => {
                        if (Date.now() - startTime >= WAIT_FOR_EMAILS_TIMEOUT_MS) {
                            clearWaitNextInterval();
                            resolve();
                        }
                        if (currentMailbox.emails.next.length > 0) {
                            shiftEmailPagesForward();
                            clearWaitNextInterval();
                            resolve();
                        }
                    }, PAGINATE_MAILBOX_CHECK_DELAY_MS);
                }
            }
        });
    }
</script>

<script lang="ts">
    import { showView } from "$lib/stores/mainNav.svelte";
    import type { Account } from "$lib/types";

    setContext<MailboxContext>(CONTEXT_KEY, {
        currentOffset,
        emailSelection,
        getGroupedUidSelection: () => groupedUidSelection,
    });

    let emails = $derived(currentMailbox?.emails.current ?? []);
    let unreadEmails = $derived(emails.filter(e => !(e.flags ?? []).includes("\\Seen")));
    let readEmails = $derived(emails.filter(e => (e.flags ?? []).includes("\\Seen")));

    let currentAccount = $derived(
        SharedStore.currentAccount !== "home"
            ? (SharedStore.currentAccount as Account)
            : SharedStore.accounts[0],
    );

    function formatTime(dateStr: string): string {
        if (!dateStr) return "";
        const d = new Date(dateStr);
        const now = new Date();
        const diffMs = now.getTime() - d.getTime();
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (diffDays === 0) {
            return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
        } else if (diffDays === 1) {
            return "Yesterday";
        } else if (diffDays < 7) {
            return d.toLocaleDateString([], { weekday: "short" });
        } else {
            return d.toLocaleDateString([], { month: "short", day: "numeric" });
        }
    }

    function getSenderName(email: any): string {
        const from = email.from || email.sender || "";
        const match = from.match(/"?([^"<]+)"?\s*</);
        return match ? match[1].trim() : from.split("@")[0] || "Unknown";
    }

    function getSubject(email: any): string {
        return email.subject || "(no subject)";
    }

    function isUnread(email: any): boolean {
        return !(email.flags ?? []).includes("\\Seen");
    }

    function openEmail(email: any) {
        showView("inbox");
    }
</script>

<!-- Header Toolbar -->
<header class="h-14 border-b border-notion-border dark:border-notion-border-dark px-6 flex items-center justify-between flex-shrink-0 bg-white/80 dark:bg-[#121212]/80 backdrop-blur">
    <div class="flex items-center space-x-3">
        <div class="flex items-center space-x-2.5">
            <div class="w-6 h-6 rounded flex items-center justify-center text-red-500">
                <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>
            </div>
            <h1 class="text-base font-semibold text-gray-900 dark:text-white">Inbox</h1>
        </div>
    </div>
    <div class="flex items-center space-x-2">
        <button class="flex items-center space-x-1.5 px-3 py-1 rounded-md border border-gray-200 dark:border-gray-700 hover:bg-notion-hover dark:hover:bg-notion-hover-dark text-xs font-medium text-gray-700 dark:text-gray-300 shadow-xs transition-colors">
            <svg class="w-3.5 h-3.5 text-amber-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>
            <span>Auto label</span>
        </button>
        <button class="p-1.5 text-notion-text-muted hover:text-gray-800 dark:hover:text-gray-200 hover:bg-notion-hover dark:hover:bg-notion-hover-dark rounded-md transition-colors" title="Filter & Sort">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="21" x2="14" y1="4" y2="4"/><line x1="10" x2="3" y1="4" y2="4"/><line x1="21" x2="12" y1="12" y2="12"/><line x1="8" x2="3" y1="12" y2="12"/><line x1="21" x2="16" y1="20" y2="20"/><line x1="12" x2="3" y1="20" y2="20"/><line x1="14" x2="14" y1="2" y2="6"/><line x1="8" x2="8" y1="10" y2="14"/><line x1="16" x2="16" y1="18" y2="22"/></svg>
        </button>
        <button class="p-1.5 text-notion-text-muted hover:text-gray-800 dark:hover:text-gray-200 hover:bg-notion-hover dark:hover:bg-notion-hover-dark rounded-md transition-colors" title="Settings" onclick={() => showView("settings")}>
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.01a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z"/></svg>
        </button>
    </div>
</header>

<!-- Email List -->
<div class="flex-1 overflow-y-auto px-6 py-4 space-y-6">
    <!-- Unread Section -->
    {#if unreadEmails.length > 0}
        <div>
            <div class="flex items-center space-x-2 text-xs font-medium text-notion-text-muted mb-2 cursor-pointer select-none">
                <svg class="w-3.5 h-3.5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>
                <span class="text-xs font-semibold text-gray-700 dark:text-gray-300">Unread</span>
                <svg class="w-3.5 h-3.5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>
            </div>
            <div class="space-y-0.5 divide-y divide-gray-100 dark:divide-gray-800/60">
                {#each unreadEmails as email}
                    <button
                        class="group flex items-center justify-between py-2.5 px-2 hover:bg-notion-hover dark:hover:bg-notion-hover-dark rounded-md cursor-pointer transition-colors w-full text-left"
                        onclick={() => openEmail(email)}
                    >
                        <div class="flex items-center space-x-3 min-w-0 pr-4">
                            <span class="w-2 h-2 rounded-full bg-blue-500 flex-shrink-0"></span>
                            <span class="font-semibold text-sm text-gray-900 dark:text-gray-100 w-36 truncate flex-shrink-0">{getSenderName(email)}</span>
                            <span class="text-sm text-gray-700 dark:text-gray-300 truncate font-normal">{getSubject(email)}</span>
                        </div>
                        <div class="flex items-center space-x-3 flex-shrink-0">
                            <span class="text-xs text-notion-text-muted w-16 text-right">{formatTime(email.date)}</span>
                        </div>
                    </button>
                {/each}
            </div>
        </div>
    {:else}
        <div class="py-4 text-xs text-notion-text-muted italic">No unread messages</div>
    {/if}

    <!-- Read Section -->
    {#if readEmails.length > 0}
        <div class="pt-2">
            <div class="flex items-center space-x-2 text-xs font-medium text-notion-text-muted mb-2 cursor-pointer select-none">
                <svg class="w-3.5 h-3.5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
                <span class="text-xs font-semibold text-gray-700 dark:text-gray-300">Read</span>
                <svg class="w-3.5 h-3.5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>
            </div>
            <div class="space-y-0.5 divide-y divide-gray-100 dark:divide-gray-800/60">
                {#each readEmails as email}
                    <button
                        class="group flex items-center justify-between py-2.5 px-2 hover:bg-notion-hover dark:hover:bg-notion-hover-dark rounded-md cursor-pointer transition-colors w-full text-left"
                        onclick={() => openEmail(email)}
                    >
                        <div class="flex items-center space-x-3 min-w-0 pr-4">
                            <span class="w-2 h-2"></span>
                            <span class="font-medium text-sm text-gray-900 dark:text-gray-100 w-36 truncate flex-shrink-0">{getSenderName(email)}</span>
                            <span class="text-sm text-gray-700 dark:text-gray-300 truncate font-normal">{getSubject(email)}</span>
                        </div>
                        <div class="flex items-center space-x-3 flex-shrink-0">
                            <span class="text-xs text-notion-text-muted w-16 text-right">{formatTime(email.date)}</span>
                        </div>
                    </button>
                {/each}
            </div>
        </div>
    {:else}
        <div class="pt-2 text-xs text-notion-text-muted italic">No read messages</div>
    {/if}

    {#if emails.length === 0}
        <div class="flex flex-col items-center justify-center py-16 text-notion-text-muted">
            <svg class="w-12 h-12 mb-4 opacity-30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>
            <p class="text-sm">No messages in this folder</p>
        </div>
    {/if}
</div>
