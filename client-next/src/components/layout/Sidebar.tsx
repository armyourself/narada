"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMainNav, type MainView } from "@/lib/stores/mainNav";
import { useSharedStore } from "@/lib/stores/shared";
import { show as showMessage, openCompose, openSettings } from "@/lib/stores/ui";
import { PreferenceManager, Theme } from "@/lib/preferences";
import { MailboxController } from "@/lib/mailbox";
import { getCurrentMailbox } from "@/lib/mailbox/getCurrentMailbox";
import { openEmailInPane } from "@/lib/mailbox/openEmail";
import {
    formatListTime,
    getSenderName,
    getSnippet,
    getSubject,
    isUnread,
} from "@/lib/mailbox/display";
import { local } from "@/lib/locales";
import { DEFAULT_LANGUAGE } from "@/lib/constants";
import type { Account } from "@/lib/types";

interface NavItem {
    id: string;
    view: string;
    label: string;
    icon: string;
    badge?: number;
    folder?: string;
}

const views: NavItem[] = [
    { id: "inbox", view: "inbox", label: "Inbox", icon: "inbox", folder: "Inbox" },
];

const mailFolders: NavItem[] = [
    { id: "all-mail", view: "all-mail", label: "All Mail", icon: "archive", folder: "All" },
    { id: "sent", view: "sent", label: "Sent", icon: "send", folder: "Sent" },
    { id: "drafts", view: "drafts", label: "Drafts", icon: "file-edit", folder: "Drafts" },
    { id: "spam", view: "spam", label: "Spam", icon: "ban", folder: "Spam" },
    { id: "trash", view: "trash", label: "Trash", icon: "trash", folder: "Trash" },
    { id: "starred", view: "starred", label: "Starred", icon: "star", folder: "Flagged" },
    { id: "encrypted", view: "encrypted", label: "Encrypted", icon: "lock", folder: "Encrypted" },
];

const ICON_PATHS: Record<string, ReactNode> = {
    inbox: (
        <>
            <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
            <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
        </>
    ),
    send: (
        <>
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </>
    ),
    "file-edit": (
        <>
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
        </>
    ),
    archive: (
        <>
            <polyline points="21 8 21 21 3 21 3 8" />
            <rect x="1" y="3" width="22" height="5" rx="1" />
            <line x1="10" y1="12" x2="14" y2="12" />
        </>
    ),
    star: (
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    ),
    lock: (
        <>
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </>
    ),
    ban: (
        <>
            <circle cx="12" cy="12" r="10" />
            <line x1="4.9" x2="19.1" y1="4.9" y2="19.1" />
        </>
    ),
    trash: (
        <>
            <path d="M3 6h18" />
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
            <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
        </>
    ),
    search: (
        <>
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
        </>
    ),
};

function NavIcon({ name, className }: { name: string; className?: string }) {
    return (
        <svg
            className={className ?? "w-4 h-4 text-notion-text-muted"}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            {ICON_PATHS[name]}
        </svg>
    );
}

export default function Sidebar() {
    const mainNav = useMainNav();
    const accounts = useSharedStore((s) => s.accounts);
    const currentAccountState = useSharedStore((s) => s.currentAccount);
    const mailboxes = useSharedStore((s) => s.mailboxes);
    const server = useSharedStore((s) => s.server);

    const [isDark, setIsDark] = useState(false);
    const [relayCount, setRelayCount] = useState(0);
    const [relaysConnected, setRelaysConnected] = useState(false);
    const [showProfileMenu, setShowProfileMenu] = useState(false);
    const [searchOpen, setSearchOpen] = useState(false);

    const currentAccount: Account | undefined =
        currentAccountState !== "home" ? currentAccountState : accounts[0];

    const accountInitial = accounts.length > 0
        ? (accounts[0].fullname || accounts[0].email_address)[0].toUpperCase()
        : "?";
    const accountName = accounts.length > 0
        ? accounts[0].fullname || accounts[0].email_address
        : "No account";
    const accountEmail = accounts.length > 0 ? accounts[0].email_address : "";

    const unreadCount = useMemo(() => {
        const mailbox = mailboxes[currentAccount?.email_address ?? ""];
        if (!mailbox) return 0;
        return mailbox.emails.current.filter(
            (email) => !(email.flags ?? []).includes("\\Seen"),
        ).length;
    }, [mailboxes, currentAccount]);

    // Live results for the search palette (mockup F14) over the same
    // folder list the mailbox shows. The full list behind the palette
    // filters too, so picking a result resets the query.
    const currentMailbox = useMemo(
        () => getCurrentMailbox({ mailboxes, currentAccount: currentAccountState }),
        [mailboxes, currentAccountState],
    );
    const paletteQuery = mainNav.searchQuery.trim().toLowerCase();
    // Cheap filter/slice — the compiler memoizes it; a manual useMemo here
    // conflicts with the inferred deps (compiler vs exhaustive-deps).
    const paletteResults = (() => {
        if (!paletteQuery) return [];
        const list = currentMailbox?.emails.current ?? [];
        return list
            .filter(
                (email) =>
                    getSenderName(email).toLowerCase().includes(paletteQuery) ||
                    getSubject(email).toLowerCase().includes(paletteQuery) ||
                    getSnippet(email).toLowerCase().includes(paletteQuery),
            )
            .slice(0, 8);
    })();

    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect -- DOM state is only readable after mount
        setIsDark(document.documentElement.classList.contains("dark"));
    }, []);

    useEffect(() => {
        let active = true;
        const fetchRelayStatus = async () => {
            try {
                const res = await fetch(`${server}/nostr/relays`);
                const json = await res.json();
                if (!active) return;
                if (json.success && Array.isArray(json.data)) {
                    const count = json.data.filter((r: { connected: boolean }) => r.connected).length;
                    setRelayCount(count);
                    setRelaysConnected(count > 0);
                }
            } catch {
                if (!active) return;
                setRelayCount(0);
                setRelaysConnected(false);
            }
        };
        fetchRelayStatus();
        const interval = setInterval(fetchRelayStatus, 30000);
        return () => {
            active = false;
            clearInterval(interval);
        };
    }, [server]);

    useEffect(() => {
        const onWindowClick = () => setShowProfileMenu(false);
        window.addEventListener("click", onWindowClick);
        return () => window.removeEventListener("click", onWindowClick);
    }, []);

    const selectFolder = async (item: NavItem) => {
        mainNav.showView("inbox");
        mainNav.selectFolder(item.folder ?? item.id);
        if (!item.folder || !currentAccount) return;
        const response = await MailboxController.getMailbox(currentAccount, item.folder);
        if (!response.success) {
            showMessage({ title: local.error_get_mailbox[DEFAULT_LANGUAGE] });
        }
    };

    const selectView = (item: NavItem) => {
        if (item.folder) {
            void selectFolder(item);
        } else {
            mainNav.showView(item.view as MainView);
        }
    };

    const toggleTheme = async () => {
        const next: Theme = isDark ? Theme.Light : Theme.Dark;
        await PreferenceManager.changeTheme(next);
        setIsDark(!isDark);
        document.documentElement.classList.toggle("dark", !isDark);
    };

    const goToSettings = () => {
        openSettings();
        setShowProfileMenu(false);
    };

    const isActive = (item: NavItem) =>
        mainNav.view === "inbox" && mainNav.folder === item.folder;

    const navButtonClass = (item: NavItem, baseActive: boolean) =>
        `w-full flex items-center justify-between px-2.5 py-1.5 rounded-md text-sm transition-colors ${
            baseActive
                ? "bg-notion-active font-medium text-notion-text"
                : "text-notion-text-secondary hover:bg-notion-hover"
        }`;

    return (
        <aside className="relative w-[234px] flex-shrink-0 bg-notion-sidebar border-r border-[#ffffff0e] flex flex-col justify-between h-full z-20">
            <div>
                {/* Profile Switcher */}
                <div className="p-3 pb-1">
                    <div className="flex items-center justify-between group">
                        <button
                            className="flex items-center space-x-2 hover:bg-notion-hover p-1.5 rounded-md transition-colors text-left flex-1 min-w-0 mr-1"
                            onClick={(e) => {
                                e.stopPropagation();
                                setShowProfileMenu(!showProfileMenu);
                            }}
                        >
                            <div className="w-6 h-6 rounded-full bg-notion-accent-tint text-notion-accent flex items-center justify-center text-xs font-semibold flex-shrink-0">
                                {accountInitial}
                            </div>
                            <span className="font-medium text-sm text-notion-text truncate">{accountName}</span>
                            <svg className="w-3.5 h-3.5 text-notion-text-muted flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 9 6 6 6-6" /></svg>
                        </button>

                        <button
                            className="p-1.5 text-notion-text-secondary hover:bg-notion-hover rounded-md transition-colors"
                            title="Compose new message (N)"
                            onClick={(e) => {
                                e.stopPropagation();
                                openCompose();
                            }}
                        >
                            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>
                        </button>
                    </div>

                    {/* Profile Dropdown */}
                    {showProfileMenu && (
                        <div className="absolute left-4 top-12 w-56 bg-notion-surface rounded-md shadow-notion-popover border border-notion-border p-1.5 z-50 text-xs text-notion-text">
                            <div className="px-2 py-1.5 font-medium text-notion-text-muted border-b border-notion-border mb-1">
                                {accountEmail}
                            </div>
                            <button
                                className="w-full text-left px-2 py-1.5 hover:bg-notion-hover rounded flex items-center space-x-2"
                                onClick={(e) => { e.stopPropagation(); goToSettings(); }}
                            >
                                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></svg>
                                <span>Account settings</span>
                            </button>
                            <button
                                className="w-full text-left px-2 py-1.5 hover:bg-notion-hover rounded flex items-center space-x-2"
                                onClick={(e) => { e.stopPropagation(); void toggleTheme(); }}
                            >
                                {isDark ? (
                                    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4" /></svg>
                                ) : (
                                    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" /></svg>
                                )}
                                <span>Toggle Dark Theme</span>
                            </button>
                            <div className="border-t border-notion-border my-1"></div>
                            <button className="w-full text-left px-2 py-1.5 hover:bg-notion-hover rounded text-notion-danger flex items-center space-x-2">
                                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" /></svg>
                                <span>Log out</span>
                            </button>
                        </div>
                    )}
                </div>

                {/* Search (mockup F14: palette popover under the row) */}
                <div className="px-2 pt-2 pb-1">
                    <button
                        className={`w-full flex items-center space-x-2.5 px-2.5 py-1.5 rounded-md text-sm transition-colors ${
                            mainNav.searchQuery
                                ? "bg-notion-active font-medium text-notion-text"
                                : "text-notion-text-secondary hover:bg-notion-hover"
                        }`}
                        onClick={() => setSearchOpen(true)}
                    >
                        <NavIcon name="search" className="w-4 h-4 text-notion-text-muted" />
                        <span>Search</span>
                    </button>
                    {searchOpen && (
                        <>
                            <div
                                className="fixed inset-0 z-40"
                                onClick={() => setSearchOpen(false)}
                            />
                            <div className="absolute left-2 top-[94px] w-[450px] max-w-[calc(100vw-16px)] bg-notion-surface border border-notion-border rounded-xl shadow-notion-popover overflow-hidden z-50">
                                <div className="flex items-center gap-2 px-3 py-2.5 border-b border-notion-border">
                                    <NavIcon
                                        name="search"
                                        className="w-4 h-4 text-notion-text-muted shrink-0"
                                    />
                                    <input
                                        autoFocus
                                        type="search"
                                        placeholder="Search mail"
                                        value={mainNav.searchQuery}
                                        className="w-full bg-transparent text-sm text-notion-text placeholder:text-notion-text-muted focus:outline-none"
                                        onChange={(e) => mainNav.setSearchQuery(e.target.value)}
                                        onKeyDown={(e) => {
                                            if (e.key === "Escape") {
                                                mainNav.setSearchQuery("");
                                                setSearchOpen(false);
                                            }
                                        }}
                                    />
                                </div>
                                <div className="max-h-80 overflow-y-auto py-1">
                                    {paletteResults.length === 0 ? (
                                        <div className="px-3 py-3 text-xs text-notion-text-muted">
                                            {paletteQuery
                                                ? "No messages match your search."
                                                : "Start typing to search this folder."}
                                        </div>
                                    ) : (
                                        paletteResults.map((email) => (
                                            <button
                                                key={`${email.uid}|${email.message_id}`}
                                                className="w-full text-left px-3 py-2 flex items-center gap-2.5 hover:bg-notion-hover"
                                                onClick={() => {
                                                    openEmailInPane(email);
                                                    mainNav.setSearchQuery("");
                                                    setSearchOpen(false);
                                                }}
                                            >
                                                <span
                                                    className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                                                        isUnread(email)
                                                            ? "bg-notion-accent"
                                                            : "bg-transparent"
                                                    }`}
                                                />
                                                <span className="min-w-0 flex-1 flex flex-col">
                                                    <span className="flex items-baseline gap-2 min-w-0">
                                                        <span className="text-sm font-semibold text-notion-text truncate">
                                                            {getSenderName(email)}
                                                        </span>
                                                        <span className="text-sm text-notion-text truncate">
                                                            {getSubject(email)}
                                                        </span>
                                                    </span>
                                                    <span className="text-xs text-notion-text-muted truncate">
                                                        {getSnippet(email)}
                                                    </span>
                                                </span>
                                                <span className="text-xs text-notion-text-muted shrink-0">
                                                    {formatListTime(email.date)}
                                                </span>
                                            </button>
                                        ))
                                    )}
                                </div>
                            </div>
                        </>
                    )}
                </div>

                {/* Views Navigation */}
                <div className="px-2 pt-3 pb-1">
                    <div className="px-2 py-1 text-xs font-normal text-notion-text-muted">Views</div>
                    <nav className="space-y-0.5 mt-0.5">
                        {views.map((item) => (
                            <button
                                key={item.id}
                                className={navButtonClass(item, isActive(item))}
                                onClick={() => selectView(item)}
                            >
                                <div className="flex items-center space-x-2.5 min-w-0">
                                    <NavIcon
                                        name={item.icon}
                                        className={`w-4 h-4 ${isActive(item) ? "text-notion-text" : "text-notion-text-muted"}`}
                                    />
                                    <span className="truncate">{item.label}</span>
                                </div>
                                {item.id === "inbox" && unreadCount > 0 && (
                                    <span className="text-xs text-notion-text-muted font-normal">{unreadCount}</span>
                                )}
                            </button>
                        ))}
                    </nav>
                </div>

                {/* Mail Section */}
                <div className="px-2 pt-3 pb-1">
                    <div className="px-2 py-1 text-xs font-normal text-notion-text-muted">Mail</div>
                    <nav className="space-y-0.5 mt-0.5">
                        {mailFolders.map((item) => (
                            <button
                                key={item.id}
                                className={navButtonClass(item, isActive(item))}
                                onClick={() => selectView(item)}
                            >
                                <div className="flex items-center space-x-2.5 min-w-0">
                                    <NavIcon
                                        name={item.icon}
                                        className={`w-4 h-4 ${isActive(item) ? "text-notion-text" : "text-notion-text-muted"}`}
                                    />
                                    <span className="truncate">{item.label}</span>
                                </div>
                            </button>
                        ))}
                    </nav>
                </div>
            </div>

            {/* Sidebar Footer */}
            <div className="p-3 border-t border-notion-border flex items-center justify-between text-notion-text-muted">
                <div className="flex items-center space-x-1.5">
                    <div className="text-[10px] font-semibold text-notion-text-secondary">
                        {relaysConnected ? (
                            <span className="text-notion-success">
                                {relayCount} relay{relayCount !== 1 ? "s" : ""}
                            </span>
                        ) : (
                            <span>offline</span>
                        )}
                    </div>
                </div>
                <button
                    className="w-6 h-6 hover:bg-notion-hover rounded flex items-center justify-center text-notion-text-muted hover:text-notion-text transition-colors"
                    onClick={goToSettings}
                    title="Settings"
                >
                    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.01a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" /></svg>
                </button>
            </div>
        </aside>
    );
}
