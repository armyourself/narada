"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { closePalette, openCompose, openSettings } from "@/lib/stores/ui";
import { MailboxController } from "@/lib/mailbox/MailboxController";
import { openEmailInPane } from "@/lib/mailbox/openEmail";
import {
    formatListTime,
    getSenderName,
    getSnippet,
    getSubject,
} from "@/lib/mailbox/display";
import { useSharedStore } from "@/lib/stores/shared";
import type { SearchResult } from "@/lib/types";

interface Command {
    label: string;
    icon: string;
    shortcut?: string;
    category: string;
    action?: () => void;
}

const SEARCH_DEBOUNCE_MS = 300;
const SEARCH_RESULT_LIMIT = 8;

const ICON_PATHS: Record<string, ReactNode> = {
    "x-square": (
        <>
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path d="m9 9 6 6" />
            <path d="m15 9-6 6" />
        </>
    ),
    "arrow-left": (
        <>
            <path d="m12 19-7-7 7-7" />
            <path d="M19 12H5" />
        </>
    ),
    "arrow-right": (
        <>
            <path d="M5 12h14" />
            <path d="m12 5 7 7-7 7" />
        </>
    ),
    mail: (
        <>
            <rect x="2" y="4" width="20" height="16" rx="2" />
            <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
        </>
    ),
    "check-square": (
        <>
            <polyline points="9 11 12 14 22 4" />
            <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
        </>
    ),
    "corner-up-right": (
        <>
            <polyline points="15 14 20 9 15 4" />
            <path d="M4 20v-7a4 4 0 0 1 4-4h12" />
        </>
    ),
    "corner-up-left": (
        <>
            <polyline points="9 14 4 9 9 4" />
            <path d="M20 20v-7a4 4 0 0 0-4-4H4" />
        </>
    ),
    "reply-all": (
        <>
            <polyline points="7 17 2 12 7 7" />
            <polyline points="12 17 7 12 12 7" />
            <path d="M22 18v-2a4 4 0 0 0-4-4H7" />
        </>
    ),
    pencil: (
        <>
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
        </>
    ),
    settings: (
        <>
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </>
    ),
};

function buildCommands(): Command[] {
    return [
        { label: "Close thread", icon: "x-square", shortcut: "Escape", category: "Thread" },
        { label: "Previous thread", icon: "arrow-left", shortcut: "K", category: "Thread" },
        { label: "Next thread", icon: "arrow-right", shortcut: "J", category: "Thread" },
        { label: "Mark as unread", icon: "mail", shortcut: "Shift+U", category: "Thread" },
        { label: "Mark as read or unread", icon: "check-square", shortcut: "U", category: "Thread" },
        { label: "Forward", icon: "corner-up-right", shortcut: "F", category: "Thread" },
        { label: "Reply", icon: "corner-up-left", shortcut: "R", category: "Thread" },
        { label: "Reply all", icon: "reply-all", shortcut: "A", category: "Thread" },
        {
            label: "Compose new message",
            icon: "pencil",
            shortcut: "N",
            category: "Navigate",
            action: () => openCompose(),
        },
        {
            label: "Go to settings",
            icon: "settings",
            category: "Navigate",
            action: () => openSettings(),
        },
    ];
}

export default function CommandPalette() {
    const [query, setQuery] = useState("");
    const [results, setResults] = useState<SearchResult[]>([]);
    const [searching, setSearching] = useState(false);
    const searchIdRef = useRef(0);
    const commands = useMemo(() => buildCommands(), []);

    // Debounced cross-account search (POST /search-all). Results are only
    // rendered while the query is long enough, so no synchronous state
    // reset is needed when the user clears the input.
    useEffect(() => {
        const trimmed = query.trim();
        if (trimmed.length < 2) {
            // Invalidate any in-flight request for a longer query.
            searchIdRef.current += 1;
            return;
        }

        const searchId = ++searchIdRef.current;
        const timer = setTimeout(() => {
            setSearching(true);
            MailboxController.searchAll(trimmed, { limit: SEARCH_RESULT_LIMIT })
                .then((response) => {
                    if (searchId !== searchIdRef.current) return;
                    setResults(
                        response.success && response.data
                            ? response.data.results
                            : [],
                    );
                })
                .catch(() => {
                    if (searchId !== searchIdRef.current) return;
                    setResults([]);
                })
                .finally(() => {
                    if (searchId !== searchIdRef.current) return;
                    setSearching(false);
                });
        }, SEARCH_DEBOUNCE_MS);

        return () => clearTimeout(timer);
    }, [query]);

    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (event.key === "Escape") closePalette();
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, []);

    const filtered = useMemo(
        () =>
            query.trim()
                ? commands.filter((c) => c.label.toLowerCase().includes(query.trim().toLowerCase()))
                : commands,
        [commands, query],
    );

    const grouped = useMemo(() => {
        const categories: Record<string, Command[]> = {};
        for (const command of filtered) {
            (categories[command.category] ??= []).push(command);
        }
        return Object.entries(categories);
    }, [filtered]);

    const select = (command: Command) => {
        closePalette();
        command.action?.();
    };

    // Cross-account hit: switch to the owning account first so the
    // reading pane fetches content (and marks read) in the right mailbox.
    const selectSearchResult = (result: SearchResult) => {
        const state = useSharedStore.getState();
        const owner = state.accounts.find(
            (account) => account.email_address === result.account,
        );
        if (owner && state.currentAccount !== owner) {
            useSharedStore.setState({ currentAccount: owner });
        }
        closePalette();
        openEmailInPane(result);
    };

    const searchActive = query.trim().length >= 2;

    return (
        <div
            className="fixed inset-0 bg-black/55 backdrop-blur-[2px] z-50 flex items-start justify-center pt-20 px-4"
            onClick={closePalette}
        >
            <div
                className="bg-notion-surface w-full max-w-[576px] rounded-xl shadow-notion-popover border border-notion-border overflow-hidden flex flex-col"
                onClick={(event) => event.stopPropagation()}
            >
                {/* Input */}
                <div className="flex items-center px-4 py-3 border-b border-notion-border">
                    <svg
                        className="w-4 h-4 text-notion-text-muted mr-3 flex-shrink-0"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                    >
                        <circle cx="11" cy="11" r="8" />
                        <path d="m21 21-4.3-4.3" />
                    </svg>
                    <input
                        autoFocus
                        type="text"
                        placeholder="Search commands or Narada..."
                        className="w-full bg-transparent text-sm text-notion-text focus:outline-none placeholder:text-notion-text-muted"
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                    />
                </div>

                {/* Command list */}
                <div className="max-h-96 overflow-y-auto p-1 space-y-1">
                    {searchActive && (
                        <div>
                            <div className="px-3 py-1.5 text-[11px] font-semibold text-notion-text-muted uppercase tracking-wider">
                                {searching ? "Searching..." : "Messages"}
                            </div>
                            {results.map((result) => (
                                <button
                                    key={`${result.account}:${result.uid}`}
                                    type="button"
                                    className="w-full flex items-start gap-3 px-3 py-2 rounded-md hover:bg-notion-hover text-left"
                                    onClick={() => selectSearchResult(result)}
                                >
                                    <svg
                                        className="w-4 h-4 text-notion-text-muted mt-0.5 flex-shrink-0"
                                        viewBox="0 0 24 24"
                                        fill="none"
                                        stroke="currentColor"
                                        strokeWidth="2"
                                    >
                                        {ICON_PATHS.mail}
                                    </svg>
                                    <span className="min-w-0 flex-1">
                                        <span className="flex items-baseline justify-between gap-2">
                                            <span className="text-sm text-notion-text truncate">
                                                {getSenderName(result)}
                                            </span>
                                            <span className="text-xs text-notion-text-muted flex-shrink-0">
                                                {formatListTime(result.date)}
                                            </span>
                                        </span>
                                        <span className="block text-sm text-notion-text truncate">
                                            {getSubject(result)}
                                        </span>
                                        <span className="block text-xs text-notion-text-muted truncate">
                                            {getSnippet(result)}
                                        </span>
                                    </span>
                                    <span className="text-[11px] text-notion-text-muted flex-shrink-0 mt-0.5">
                                        {result.account}
                                    </span>
                                </button>
                            ))}
                            {!searching && results.length === 0 && (
                                <div className="px-3 py-2 text-sm text-notion-text-muted">
                                    No messages found
                                </div>
                            )}
                        </div>
                    )}
                    {grouped.length > 0 ? (
                        grouped.map(([category, items]) => (
                            <div key={category}>
                                <div className="px-3 py-1.5 text-[11px] font-semibold text-notion-text-muted uppercase tracking-wider">
                                    {category}
                                </div>
                                {items.map((command) => (
                                    <button
                                        key={command.label}
                                        type="button"
                                        className="w-full flex items-center justify-between px-3 py-2 rounded-md hover:bg-notion-hover text-left"
                                        onClick={() => select(command)}
                                    >
                                        <div className="flex items-center space-x-3">
                                            <svg
                                                className="w-4 h-4 text-notion-text-muted"
                                                viewBox="0 0 24 24"
                                                fill="none"
                                                stroke="currentColor"
                                                strokeWidth="2"
                                                strokeLinecap="round"
                                                strokeLinejoin="round"
                                            >
                                                {ICON_PATHS[command.icon]}
                                            </svg>
                                            <span className="text-sm font-normal text-notion-text">
                                                {command.label}
                                            </span>
                                        </div>
                                        {command.shortcut && (
                                            <kbd className="text-xs text-notion-text-muted font-sans">
                                                {command.shortcut}
                                            </kbd>
                                        )}
                                    </button>
                                ))}
                            </div>
                        ))
                    ) : (
                        <div className="px-3 py-6 text-sm text-notion-text-muted text-center">
                            No matching commands
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="px-4 py-2 border-t border-notion-border bg-notion-surface-sunken flex items-center justify-start space-x-4 text-xs text-notion-text-muted">
                    <span className="flex items-center">
                        <svg className="w-3 h-3 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="m7 15 5 5 5-5" />
                            <path d="m7 9 5-5 5 5" />
                        </svg>
                        Select
                    </span>
                    <span className="flex items-center">
                        <svg className="w-3 h-3 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="m9 18 6-6-6-6" />
                        </svg>
                        Open
                    </span>
                </div>
            </div>
        </div>
    );
}
