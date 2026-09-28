"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMainNav } from "@/lib/stores/mainNav";
import { useSharedStore } from "@/lib/stores/shared";
import { show as showMessage, showToast } from "@/lib/stores/ui";
import { getCurrentMailbox } from "@/lib/mailbox/getCurrentMailbox";
import { openEmailInPane } from "@/lib/mailbox/openEmail";
import {
    formatListTime as formatTime,
    getSenderName,
    getSnippet,
    getSubject,
    isUnread,
} from "@/lib/mailbox/display";
import { MailboxController } from "@/lib/mailbox";
import { local } from "@/lib/locales";
import { DEFAULT_LANGUAGE } from "@/lib/constants";
import type { Account, Email, SearchCriteria } from "@/lib/types";
import type { DeliveryRoute } from "@/lib/stores/mainNav";
import RouteBadge, { emailDeliveryRoute, routeMeta } from "@/components/views/RouteBadge";
import ReadingPane from "./ReadingPane";
import SearchPanel from "./SearchPanel";

interface ChipProps {
    label: string;
    active?: boolean;
    chevron?: boolean;
    onClick?: () => void;
}

function Chip({ label, active, chevron, onClick }: ChipProps) {
    return (
        <button
            className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-md border text-xs font-medium transition-colors ${
                active
                    ? "border-notion-accent text-notion-accent bg-notion-accent-tint"
                    : "border-notion-border text-notion-text-secondary hover:bg-notion-hover"
            }`}
            onClick={onClick}
        >
            <span>{label}</span>
            {chevron && (
                <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 9 6 6 6-6" /></svg>
            )}
        </button>
    );
}

function EmailRow({ email, onOpen }: { email: Email; onOpen: (email: Email) => void }) {
    const unread = isUnread(email);
    const snippet = getSnippet(email);

    return (
        <button
            className="group flex items-center justify-between py-2.5 px-2 hover:bg-notion-hover rounded-md cursor-pointer transition-colors w-full text-left"
            onClick={() => onOpen(email)}
        >
            <div className="flex items-center space-x-3 min-w-0 pr-4 w-full">
                <span
                    className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${unread ? "bg-notion-accent" : "bg-transparent"}`}
                ></span>
                <span
                    className={`${unread ? "font-semibold" : "font-medium"} text-sm text-notion-text w-44 truncate flex-shrink-0`}
                >
                    {getSenderName(email)}
                </span>
                <span className="text-sm truncate min-w-0 flex-1">
                    <span className={unread ? "font-semibold text-notion-text" : "font-medium text-notion-text"}>
                        {getSubject(email)}
                    </span>
                    {snippet && (
                        <span className="text-notion-text-muted font-normal" title={snippet}>
                            {" "}{snippet}
                        </span>
                    )}
                </span>
            </div>
            <div className="flex items-center space-x-3 flex-shrink-0">
                <RouteBadge route={emailDeliveryRoute(email)} />
                <span className="text-xs text-notion-text-muted w-16 text-right">{formatTime(email.date)}</span>
            </div>
        </button>
    );
}

export default function Mailbox() {
    const mailboxes = useSharedStore((s) => s.mailboxes);
    const currentAccountState = useSharedStore((s) => s.currentAccount);
    const accounts = useSharedStore((s) => s.accounts);
    const folder = useMainNav((s) => s.folder);
    const searchQuery = useMainNav((s) => s.searchQuery);
    const routeFilter = useMainNav((s) => s.routeFilter);
    const toggleRouteFilter = useMainNav((s) => s.toggleRouteFilter);

    const [unreadOnly, setUnreadOnly] = useState(false);
    const [refreshing, setRefreshing] = useState(false);
    // Selection lives in the nav store so the search palette can open
    // messages too.
    const selected = useMainNav((s) => s.selectedEmail);
    const selectEmail = useMainNav((s) => s.selectEmail);
    const [searchOpen, setSearchOpen] = useState(false);
    const [activeSearch, setActiveSearch] = useState<SearchCriteria | null>(null);
    const [loadingMore, setLoadingMore] = useState(false);
    const loadingMoreRef = useRef(false);
    const listRef = useRef<HTMLDivElement>(null);

    const currentAccount: Account | undefined =
        currentAccountState !== "home" ? currentAccountState : accounts[0];

    const currentMailbox = useMemo(
        () => getCurrentMailbox({ mailboxes, currentAccount: currentAccountState }),
        [mailboxes, currentAccountState],
    );

    const emails = (() => {
        const list = currentMailbox?.emails.current ?? [];
        const query = searchQuery.trim().toLowerCase();
        return list.filter((email) => {
            if (unreadOnly && !isUnread(email)) return false;
            if (routeFilter && emailDeliveryRoute(email) !== routeFilter) return false;
            if (!query) return true;
            return (
                getSenderName(email).toLowerCase().includes(query) ||
                getSubject(email).toLowerCase().includes(query) ||
                getSnippet(email).toLowerCase().includes(query)
            );
        });
    })();

    // The backend pages IMAP mail but returns every Nostr record on each
    // call, so the "how much is left" math only counts IMAP-side messages.
    const currentList = currentMailbox?.emails.current ?? [];
    const nostrLoaded = currentList.filter(
        (email) => email.source === "nostr",
    ).length;
    const imapLoaded = currentList.length - nostrLoaded;
    const imapTotal = (currentMailbox?.total ?? 0) - nostrLoaded;
    const hasMore = imapLoaded < imapTotal;

    const loadMore = useCallback(async () => {
        if (loadingMoreRef.current || refreshing) return;
        const currentAccount: Account | undefined =
            currentAccountState !== "home" ? currentAccountState : accounts[0];
        if (!currentAccount) return;

        const mailbox =
            useSharedStore.getState().mailboxes[currentAccount.email_address];
        if (!mailbox) return;
        const list = mailbox.emails.current;
        const nostrCount = list.filter(
            (entry) => entry.source === "nostr",
        ).length;
        const loaded = list.length - nostrCount;
        const total = (mailbox.total ?? 0) - nostrCount;
        if (loaded >= total) return;

        loadingMoreRef.current = true;
        setLoadingMore(true);
        try {
            const result = await MailboxController.loadMoreEmails(
                currentAccount,
                folder,
                activeSearch ?? undefined,
                loaded + 1,
            );
            if (!result) return;

            const state = useSharedStore.getState();
            const target = state.mailboxes[currentAccount.email_address];
            if (!target) return;
            const seen = new Set(
                target.emails.current.map(
                    (entry) => `${entry.uid}|${entry.message_id}`,
                ),
            );
            const fresh = result.emails.filter(
                (entry) => !seen.has(`${entry.uid}|${entry.message_id}`),
            );
            if (fresh.length === 0) return;

            const timestamp = (entry: Email) => {
                const value = Date.parse(entry.date ?? "");
                return Number.isNaN(value) ? 0 : value;
            };
            const merged = [...target.emails.current, ...fresh].sort(
                (a, b) => timestamp(b) - timestamp(a),
            );
            useSharedStore.setState({
                mailboxes: {
                    ...state.mailboxes,
                    [currentAccount.email_address]: {
                        ...target,
                        total: result.total,
                        emails: { prev: [], current: merged, next: [] },
                    },
                },
            });
        } finally {
            loadingMoreRef.current = false;
            setLoadingMore(false);
        }
    }, [currentAccountState, accounts, folder, activeSearch, refreshing]);

    // A short page never fires `onScroll`, so also keep fetching while the
    // list does not fill the viewport. Re-runs only when list data changes.
    const loadedCount = currentList.length;
    useEffect(() => {
        if (loadedCount === 0 || !hasMore || refreshing) return;
        if (loadingMoreRef.current) return;
        const element = listRef.current;
        if (element && element.scrollHeight <= element.clientHeight + 1) {
            void loadMore();
        }
    }, [loadedCount, hasMore, refreshing, loadMore]);

    const onListScroll = () => {
        const element = listRef.current;
        if (!element || !hasMore || loadingMoreRef.current || refreshing) return;
        if (element.scrollTop + element.clientHeight >= element.scrollHeight - 200) {
            void loadMore();
        }
    };

    // Opening + read-state flipping now lives in lib/mailbox/openEmail so
    // the search palette shares it.

    // Dev-only: `?demo=1&open=1` auto-opens the first email for headless screenshots.
    useEffect(() => {
        if (process.env.NODE_ENV !== "development") return;
        const params = new URLSearchParams(window.location.search);
        if (!params.has("open")) return;
        const first = currentMailbox?.emails.current[0];
        if (first) openEmailInPane(first);
        // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount
    }, []);

    const refresh = async () => {
        const currentAccount: Account | undefined =
            currentAccountState !== "home" ? currentAccountState : accounts[0];
        if (!currentAccount) return;
        setRefreshing(true);
        try {
            const response = await MailboxController.getMailbox(
                currentAccount,
                folder,
                activeSearch ?? undefined,
            );
            if (!response.success) {
                showMessage({ title: local.error_get_mailbox[DEFAULT_LANGUAGE] });
            }
        } finally {
            setRefreshing(false);
        }
    };

    // Advanced search: builds a SearchCriteria the backend applies to
    // every transport (IMAP SEARCH + local Nostr record filtering).
    const runSearch = async (criteria: SearchCriteria | null) => {
        const currentAccount: Account | undefined =
            currentAccountState !== "home" ? currentAccountState : accounts[0];
        if (!currentAccount) return;
        setRefreshing(true);
        setActiveSearch(criteria);
        try {
            const response = await MailboxController.getMailbox(
                currentAccount,
                folder,
                criteria ?? undefined,
            );
            if (!response.success) {
                showMessage({ title: local.error_get_mailbox[DEFAULT_LANGUAGE] });
            }
        } finally {
            setRefreshing(false);
        }
    };

    const comingSoon = (feature: string) =>
        showToast({ content: `${feature} is being ported.` });

    const folderTitle = folder.charAt(0).toUpperCase() + folder.slice(1);

    return (
        <>
            {/* Header Toolbar */}
            <header className="h-[50px] border-b border-notion-border px-6 flex items-center justify-between flex-shrink-0 bg-notion-canvas">
                <div className="flex items-center space-x-2.5">
                    <div className="w-6 h-6 rounded flex items-center justify-center">
                        <svg className="w-5 h-5 text-notion-danger" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12" /><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" /></svg>
                    </div>
                    <h1 className="text-base font-semibold text-notion-text">{folderTitle}</h1>
                </div>
                <div className="flex items-center space-x-2">
                    <button className="flex items-center space-x-1.5 px-3 py-1 rounded-md border border-notion-border hover:bg-notion-hover text-xs font-medium text-notion-text-secondary shadow-notion-btn transition-colors">
                        <svg className="w-3.5 h-3.5 text-notion-warning" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" /></svg>
                        <span>Auto label</span>
                    </button>
                    <button
                        className={`p-1.5 rounded-md transition-colors disabled:opacity-50 ${
                            searchOpen
                                ? "text-notion-accent bg-notion-accent-tint"
                                : "text-notion-text-muted hover:text-notion-text hover:bg-notion-hover"
                        }`}
                        title="Advanced search"
                        onClick={() => setSearchOpen((value) => !value)}
                    >
                        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="21" x2="14" y1="4" y2="4" /><line x1="10" x2="3" y1="4" y2="4" /><line x1="21" x2="12" y1="12" y2="12" /><line x1="8" x2="3" y1="12" y2="12" /><line x1="21" x2="16" y1="20" y2="20" /><line x1="12" x2="3" y1="20" y2="20" /><line x1="14" x2="14" y1="2" y2="6" /><line x1="8" x2="8" y1="10" y2="14" /><line x1="16" x2="16" y1="18" y2="22" /></svg>
                    </button>
                    <button
                        className="p-1.5 text-notion-text-muted hover:text-notion-text hover:bg-notion-hover rounded-md transition-colors disabled:opacity-50"
                        title="Refresh"
                        disabled={refreshing}
                        onClick={() => void refresh()}
                    >
                        <svg
                            className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`}
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                        >
                            <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
                            <path d="M21 3v5h-5" />
                            <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
                            <path d="M8 16H3v5" />
                        </svg>
                    </button>
                </div>
            </header>

            {searchOpen && (
                <SearchPanel
                    key={JSON.stringify(activeSearch ?? {})}
                    initial={activeSearch ?? {}}
                    onApply={(criteria) => {
                        setSearchOpen(false);
                        void runSearch(criteria);
                    }}
                    onClear={() => {
                        setSearchOpen(false);
                        void runSearch(null);
                    }}
                    onClose={() => setSearchOpen(false)}
                    busy={refreshing}
                />
            )}

            {/* Filter Chips */}
            <div className="h-[42px] border-b border-notion-border px-6 flex items-center gap-2 flex-shrink-0 bg-notion-canvas">
                <Chip label="Categories" chevron onClick={() => comingSoon("Categories")} />
                <Chip label="Labels" chevron onClick={() => comingSoon("Labels")} />
                <Chip
                    label="Is unread"
                    active={unreadOnly}
                    onClick={() => setUnreadOnly((value) => !value)}
                />
                {activeSearch && (
                    <Chip
                        label="Search"
                        active
                        onClick={() => setSearchOpen(true)}
                    />
                )}
                {(["direct", "relay", "gateway"] as DeliveryRoute[]).map((route) => (
                    <Chip
                        key={route}
                        label={routeMeta[route].label}
                        active={routeFilter === route}
                        onClick={() => toggleRouteFilter(route)}
                    />
                ))}
                <Chip label="Show archived" onClick={() => comingSoon("Show archived")} />
                <Chip label="From" chevron onClick={() => comingSoon("From filter")} />
                <button
                    className="flex items-center space-x-1 px-2 py-1 rounded-md text-xs font-medium text-notion-text-secondary hover:bg-notion-hover transition-colors"
                    onClick={() => comingSoon("Filter builder")}
                >
                    <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>
                    <span>Filter</span>
                </button>
            </div>

            {/* Email List */}
            <div
                ref={listRef}
                onScroll={onListScroll}
                className="flex-1 overflow-y-auto px-6 py-3"
            >
                {emails.length > 0 ? (
                    <div className="space-y-0.5">
                        {emails.map((email) => (
                            <EmailRow
                                key={`${email.uid}-${email.message_id}`}
                                email={email}
                                onOpen={openEmailInPane}
                            />
                        ))}
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center py-16 text-notion-text-muted">
                        <svg className="w-12 h-12 mb-4 opacity-30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12" /><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" /></svg>
                        <p className="text-sm">
                            {searchQuery || activeSearch
                                ? "No messages match your search."
                                : routeFilter
                                    ? `No ${routeMeta[routeFilter].label.toLowerCase()} messages in this folder`
                                    : "No messages in this folder"}
                        </p>
                    </div>
                )}
                {loadingMore && (
                    <div className="flex items-center justify-center py-4">
                        <div className="spinner w-5 h-5" />
                    </div>
                )}
            </div>

            {selected && (
                <ReadingPane
                    email={selected}
                    account={currentAccount}
                    folder={folder}
                    onClose={() => selectEmail(null)}
                />
            )}
        </>
    );
}
