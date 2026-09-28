"use client";

import { useEffect, useState } from "react";
import { useSharedStore } from "@/lib/stores/shared";
import { closeSettings, show as showMessage, showToast, showConfirm } from "@/lib/stores/ui";
import { useNostrIdentity } from "@/lib/nostr/identity";
import { NostrIdentityService } from "@/lib/services/NostrIdentityService";
import { PreferenceManager, PreferenceStore, Theme } from "@/lib/preferences";
import { AccountController } from "@/lib/account";
import type { Account } from "@/lib/types";

type SettingsTab = "inbox" | "account" | "nostr" | "signature";

const TABS: { id: SettingsTab; label: string; icon: React.ReactNode }[] = [
    {
        id: "inbox",
        label: "Inbox",
        icon: (
            <>
                <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
                <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
            </>
        ),
    },
    {
        id: "account",
        label: "Account",
        icon: (
            <>
                <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
            </>
        ),
    },
    {
        id: "nostr",
        label: "Nostr",
        icon: (
            <>
                <path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9" />
                <path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5" />
                <circle cx="12" cy="12" r="2" />
                <path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5" />
                <path d="M19.1 4.9C23 8.8 23 15.1 19.1 19" />
            </>
        ),
    },
    {
        id: "signature",
        label: "Signature",
        icon: (
            <>
                <path d="M12 20h9" />
                <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
            </>
        ),
    },
];

const SIGNATURE_KEY = "narada.signature";

interface RelayStatus {
    url: string;
    connected: boolean;
    last_error?: string;
    last_connected_at?: string;
    reconnect_count?: number;
}

function readThemePreference(): "light" | "dark" {
    try {
        return PreferenceStore.theme === Theme.Dark ? "dark" : "light";
    } catch {
        return "light";
    }
}

function readNotificationPreference(): boolean {
    try {
        return PreferenceStore.notificationStatus !== false;
    } catch {
        return true;
    }
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <section>
            <h3 className="text-sm font-semibold text-notion-text mb-1">{title}</h3>
            <div className="flex flex-col">
                {children}
            </div>
        </section>
    );
}

function Row({
    label,
    desc,
    children,
}: {
    label: string;
    desc?: string;
    children: React.ReactNode;
}) {
    return (
        <div className="flex items-center justify-between gap-8 py-2">
            <div className="min-w-0">
                <div className="text-sm leading-5 font-medium text-notion-text">{label}</div>
                {desc && <div className="text-xs leading-4 text-notion-text-secondary mt-0.5">{desc}</div>}
            </div>
            <div className="shrink-0">{children}</div>
        </div>
    );
}

function Toggle({
    checked,
    disabled,
    onChange,
}: {
    checked: boolean;
    disabled?: boolean;
    onChange: (next: boolean) => void;
}) {
    return (
        <button
            type="button"
            role="switch"
            aria-checked={checked}
            disabled={disabled}
            onClick={() => onChange(!checked)}
            className={`w-[38px] h-[22px] p-[3px] rounded-full transition-colors flex items-center ${
                checked ? "bg-notion-accent justify-end" : "bg-notion-active justify-start"
            } ${disabled ? "opacity-60 cursor-not-allowed" : ""}`}
        >
            <span className="w-4 h-4 rounded-full bg-white shadow transition-all" />
        </button>
    );
}

function SettingsButton({
    children,
    danger,
    disabled,
    onClick,
}: {
    children: React.ReactNode;
    danger?: boolean;
    disabled?: boolean;
    onClick: () => void;
}) {
    return (
        <button
            type="button"
            disabled={disabled}
            onClick={onClick}
            className={`h-8 px-3 rounded-md text-sm font-medium transition-colors disabled:opacity-50 flex items-center ${
                danger
                    ? "text-notion-danger hover:bg-notion-danger/10"
                    : "text-notion-text-secondary hover:bg-notion-hover"
            }`}
        >
            {children}
        </button>
    );
}

export default function SettingsModal() {
    const [tab, setTab] = useState<SettingsTab>("inbox");
    const [isRotating, setIsRotating] = useState(false);
    const [isDeleting, setIsDeleting] = useState(false);
    const [themePreference, setThemePreference] = useState<"light" | "dark">(
        () => readThemePreference(),
    );
    const [notificationsEnabled, setNotificationsEnabled] = useState<boolean>(
        () => readNotificationPreference(),
    );
    const [relays, setRelays] = useState<RelayStatus[] | null>(null);
    const [relayTick, setRelayTick] = useState(0);
    const [newRelay, setNewRelay] = useState("");
    const [relayBusy, setRelayBusy] = useState(false);
    const [signature, setSignature] = useState<string>(() =>
        typeof window === "undefined"
            ? ""
            : (localStorage.getItem(SIGNATURE_KEY) ?? ""),
    );

    const server = useSharedStore((s) => s.server);
    const accounts = useSharedStore((s) => s.accounts);
    const activeAccount = useSharedStore((s) => s.currentAccount);
    const { publicId, npub, loadIdentity } = useNostrIdentity();

    const currentAccount = activeAccount !== "home" ? (activeAccount as Account) : accounts[0];
    const accountId = currentAccount?.email_address ?? "";
    const nodeId = publicId ?? "not set";

    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (event.key === "Escape") closeSettings();
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, []);

    useEffect(() => {
        let active = true;
        const loadRelays = async () => {
            try {
                const res = await fetch(`${server}/nostr/relays`);
                const json = await res.json();
                if (active && json.success && Array.isArray(json.data)) {
                    setRelays(json.data as RelayStatus[]);
                }
            } catch {
                if (active) setRelays([]);
            }
        };
        void loadRelays();
        return () => {
            active = false;
        };
    }, [server, relayTick]);

    async function changeTheme(choice: "light" | "dark") {
        await PreferenceManager.changeTheme(
            choice === "dark" ? Theme.Dark : Theme.Light,
        );
        setThemePreference(choice);
    }

    async function changeNotifications(enabled: boolean) {
        await PreferenceManager.changeNotificationStatus(enabled);
        setNotificationsEnabled(enabled);
    }

    async function copyText(value: string, announce: string) {
        try {
            await navigator.clipboard.writeText(value);
            showToast({ content: announce });
        } catch {
            /* clipboard unavailable — ignore */
        }
    }

    async function addRelay() {
        const url = newRelay.trim();
        if (!url || relayBusy) return;
        setRelayBusy(true);
        try {
            const res = await fetch(`${server}/nostr/relays`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url }),
            });
            const json = await res.json();
            if (json.success) {
                showToast({ content: json.message || "relay added" });
                setNewRelay("");
            } else {
                showMessage({ title: json.message || "failed to add relay" });
            }
        } catch {
            showMessage({ title: "failed to add relay" });
        } finally {
            setRelayBusy(false);
            setRelayTick((n) => n + 1);
        }
    }

    async function removeRelay(url: string) {
        try {
            const res = await fetch(
                `${server}/nostr/relays?url=${encodeURIComponent(url)}`,
                { method: "DELETE" },
            );
            const json = await res.json();
            if (json.success) {
                showToast({ content: json.message || "relay removed" });
            } else {
                showMessage({ title: json.message || "failed to remove relay" });
            }
        } catch {
            showMessage({ title: "failed to remove relay" });
        } finally {
            setRelayTick((n) => n + 1);
        }
    }

    async function rotateKeys() {
        if (!accountId || isRotating) return;
        setIsRotating(true);
        try {
            const result = await NostrIdentityService.rotateX25519(accountId);
            if (result) {
                await loadIdentity(accountId);
                showToast({ content: "keys rotated" });
            } else {
                showMessage({ title: "key rotation failed" });
            }
        } finally {
            setIsRotating(false);
        }
    }

    function revealMnemonic() {
        // Rotation returns a one-shot claim token; redeem it for the
        // mnemonic. The claim token is single-use, so this effectively
        // re-rolls the recovery phrase — the daemon has no read-only
        // mnemonic endpoint.
        showToast({
            content: "revealing the recovery phrase requires rotating keys — use Rotate keys",
        });
    }

    async function signOut() {
        showConfirm({
            title: "Sign out?",
            confirmText: "Sign out",
            onConfirm: async () => {
                const response = await AccountController.remove(accountId);
                if (!response.success) {
                    showMessage({ title: "sign out failed" });
                    console.error(response.message);
                    return;
                }
                showToast({ content: "signed out" });
                closeSettings();
            },
        });
    }

    async function deleteIdentity() {
        showConfirm({
            title: "Delete node identity?",
            details: "Permanently destroys your keys. Mail addressed to you becomes undeliverable.",
            confirmText: "Delete identity",
            onConfirm: async () => {
                if (!accountId || isDeleting) return;
                setIsDeleting(true);
                try {
                    const ok = await NostrIdentityService.deleteIdentity(accountId);
                    if (ok) {
                        useNostrIdentity.setState({ publicId: null, npub: null, accountId: "" });
                        showToast({ content: "identity deleted" });
                    } else {
                        showMessage({ title: "identity deletion failed" });
                    }
                } finally {
                    setIsDeleting(false);
                }
            },
        });
    }

    function saveSignature() {
        try {
            localStorage.setItem(SIGNATURE_KEY, signature);
            showToast({ content: "signature saved" });
        } catch {
            showMessage({ title: "could not save signature" });
        }
    }

    const connectedRelays = (relays ?? []).filter((relay) => relay.connected).length;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div className="absolute inset-0 bg-black/55" onClick={closeSettings} aria-hidden />
            <div className="relative w-[1040px] max-w-[calc(100vw-48px)] h-[575px] max-h-[calc(100vh-48px)] bg-notion-surface rounded-xl overflow-hidden flex">
                {/* Left nav (mockup F3: w-248 dark rail) */}
                <nav className="w-[248px] shrink-0 bg-notion-sidebar flex flex-col p-3">
                    <div className="h-6 pl-3 flex items-center text-xs leading-4 font-semibold text-notion-text-secondary mb-1">
                        Account
                    </div>
                    <div className="space-y-1.5">
                        {TABS.map((item) => (
                            <button
                                key={item.id}
                                type="button"
                                className={`w-full flex items-center gap-2 h-7 pl-2.5 rounded-[4px] text-sm transition-colors ${
                                    tab === item.id
                                        ? "bg-notion-active font-medium text-notion-text"
                                        : "text-notion-text-secondary hover:bg-notion-hover"
                                }`}
                                onClick={() => setTab(item.id)}
                            >
                                <svg
                                    className={`w-5 h-5 ${tab === item.id ? "text-notion-text" : "text-notion-text-muted"}`}
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                >
                                    {item.icon}
                                </svg>
                                {item.label}
                            </button>
                        ))}
                    </div>
                </nav>

                {/* Content */}
                <div className="flex-1 overflow-y-auto px-12 py-[34px]">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-[17px]/[22px] font-semibold text-notion-text">
                            {TABS.find((item) => item.id === tab)?.label}
                        </h2>
                        <button
                            type="button"
                            aria-label="Close settings"
                            className="w-6 h-6 rounded flex items-center justify-center text-notion-text-muted hover:bg-notion-hover hover:text-notion-text"
                            onClick={closeSettings}
                        >
                            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M18 6 6 18" />
                                <path d="m6 6 12 12" />
                            </svg>
                        </button>
                    </div>
                    <div className="h-px bg-[#ffffff21] mb-4" />
                    <div className="flex flex-col gap-4">
                    {tab === "inbox" && (
                        <>
                            <Section title="Appearance">
                                <Row label="Theme" desc="Switch between light and dark.">
                                    <div className="flex rounded-md overflow-hidden border border-notion-border">
                                        <button
                                            type="button"
                                            className={`px-3 py-1.5 text-xs transition-colors ${
                                                themePreference === "light"
                                                    ? "bg-notion-accent text-white"
                                                    : "text-notion-text-secondary hover:bg-notion-hover"
                                            }`}
                                            onClick={() => void changeTheme("light")}
                                        >
                                            Light
                                        </button>
                                        <button
                                            type="button"
                                            className={`px-3 py-1.5 text-xs transition-colors border-l border-notion-border ${
                                                themePreference === "dark"
                                                    ? "bg-notion-accent text-white"
                                                    : "text-notion-text-secondary hover:bg-notion-hover"
                                            }`}
                                            onClick={() => void changeTheme("dark")}
                                        >
                                            Dark
                                        </button>
                                    </div>
                                </Row>
                            </Section>
                            <Section title="Notifications">
                                <Row
                                    label="Desktop notifications"
                                    desc="Show a banner when new mail arrives."
                                >
                                    <Toggle
                                        checked={notificationsEnabled}
                                        onChange={(next) => void changeNotifications(next)}
                                    />
                                </Row>
                                <Row
                                    label="Read receipts"
                                    desc="Let senders see a signed delivery acknowledgement."
                                >
                                    <Toggle checked disabled onChange={() => {}} />
                                </Row>
                            </Section>
                        </>
                    )}

                    {tab === "account" && (
                        <>
                            <Section title="Node identity">
                                <Row label="Your node id" desc="Ed25519 public key of this account.">
                                    <div className="flex items-center gap-2">
                                        <code className="max-w-[220px] truncate text-xs text-notion-text-muted bg-notion-surface-sunken px-2 py-1 rounded">
                                            {nodeId}
                                        </code>
                                        <SettingsButton
                                            onClick={() => void copyText(nodeId, "node id copied")}
                                        >
                                            Copy
                                        </SettingsButton>
                                    </div>
                                </Row>
                                <Row
                                    label="Recovery phrase"
                                    desc={"12-word mnemonic — write it down, don't screenshot it."}
                                >
                                    <SettingsButton onClick={() => void revealMnemonic()}>
                                        Reveal
                                    </SettingsButton>
                                </Row>
                                <Row
                                    label="Key rotation"
                                    desc="Rotate your signing key without changing your address."
                                >
                                    <SettingsButton
                                        disabled={isRotating || !accountId}
                                        onClick={() => void rotateKeys()}
                                    >
                                        {isRotating ? "Rotating…" : "Rotate keys"}
                                    </SettingsButton>
                                </Row>
                            </Section>
                            <Section title="Danger zone">
                                <Row
                                    label="Sign out"
                                    desc={"You'll need your recovery phrase to sign back in."}
                                >
                                    <SettingsButton danger onClick={() => void signOut()}>
                                        Sign out
                                    </SettingsButton>
                                </Row>
                                <Row
                                    label="Delete node identity"
                                    desc="Permanently destroys your keys. Mail addressed to you becomes undeliverable."
                                >
                                    <SettingsButton
                                        danger
                                        disabled={isDeleting || !accountId}
                                        onClick={() => void deleteIdentity()}
                                    >
                                        {isDeleting ? "Deleting…" : "Delete identity"}
                                    </SettingsButton>
                                </Row>
                            </Section>
                        </>
                    )}

                    {tab === "nostr" && (
                        <>
                            <Section title="Identity">
                                <Row label="npub" desc="Your Nostr address for npub recipients.">
                                    <div className="flex items-center gap-2">
                                        <code className="max-w-[240px] truncate text-xs text-notion-text-muted bg-notion-surface-sunken px-2 py-1 rounded">
                                            {npub ?? "no identity registered"}
                                        </code>
                                        {npub && (
                                            <SettingsButton
                                                onClick={() => void copyText(npub, "npub copied")}
                                            >
                                                Copy
                                            </SettingsButton>
                                        )}
                                    </div>
                                </Row>
                            </Section>
                            <Section title="Relays">
                                <Row
                                    label="Status"
                                    desc={
                                        relays === null
                                            ? "Loading relay status…"
                                            : `${connectedRelays} of ${relays.length} relays connected`
                                    }
                                >
                                    <SettingsButton onClick={() => setRelayTick((n) => n + 1)}>
                                        Refresh
                                    </SettingsButton>
                                </Row>
                                <Row
                                    label="Add relay"
                                    desc="ws:// or wss:// endpoint — applied to every identity immediately."
                                >
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="text"
                                            value={newRelay}
                                            placeholder="wss://relay.example.com"
                                            className="h-8 w-56 px-2 rounded-md border border-notion-border bg-notion-surface text-sm text-notion-text placeholder:text-notion-text-muted focus:outline-none focus:ring-1 focus:ring-notion-accent"
                                            onChange={(event) => setNewRelay(event.target.value)}
                                            onKeyDown={(event) => {
                                                if (event.key === "Enter") void addRelay();
                                            }}
                                        />
                                        <SettingsButton
                                            disabled={relayBusy || !newRelay.trim()}
                                            onClick={() => void addRelay()}
                                        >
                                            {relayBusy ? "Adding…" : "Add"}
                                        </SettingsButton>
                                    </div>
                                </Row>
                                {(relays ?? []).map((relay) => (
                                    <div
                                        key={relay.url}
                                        className="flex items-center gap-2.5 py-2"
                                    >
                                        <span
                                            className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                                                relay.connected
                                                    ? "bg-notion-success"
                                                    : "bg-notion-text-muted"
                                            }`}
                                            title={relay.connected ? "connected" : "disconnected"}
                                        />
                                        <span className="min-w-0 flex-1 truncate text-sm text-notion-text-secondary">
                                            {relay.url}
                                        </span>
                                        <span className="text-xs text-notion-text-muted shrink-0">
                                            {relay.connected ? "connected" : relay.last_error || "offline"}
                                        </span>
                                        <button
                                            type="button"
                                            aria-label={`Remove relay ${relay.url}`}
                                            className="w-6 h-6 rounded flex items-center justify-center text-notion-text-muted hover:text-notion-danger hover:bg-notion-hover transition-colors shrink-0"
                                            onClick={() => void removeRelay(relay.url)}
                                        >
                                            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                <path d="M18 6 6 18" />
                                                <path d="m6 6 12 12" />
                                            </svg>
                                        </button>
                                    </div>
                                ))}
                                {relays !== null && relays.length === 0 && (
                                    <div className="py-3 text-xs text-notion-text-muted">
                                        No relays reported — register a Nostr identity first.
                                    </div>
                                )}
                            </Section>
                            <Section title="Protocol">
                                <Row
                                    label="Transport"
                                    desc="kind 1050 encrypted mail over NIP-01 relays (NIP-04 cipher)."
                                >
                                    <span className="text-xs text-notion-success font-medium">
                                        active
                                    </span>
                                </Row>
                            </Section>
                        </>
                    )}

                    {tab === "signature" && (
                        <Section title="Signature">
                            <div>
                                <div className="text-sm text-notion-text mb-1">
                                    Default signature
                                </div>
                                <div className="text-xs text-notion-text-muted mb-3">
                                    Appended to outgoing plain-text mail.
                                </div>
                                <textarea
                                    value={signature}
                                    rows={6}
                                    placeholder={"— Sent from Narada"}
                                    className="w-full rounded-md border border-notion-border bg-notion-surface px-3 py-2 text-sm text-notion-text placeholder:text-notion-text-muted focus:outline-none focus:ring-1 focus:ring-notion-accent resize-y"
                                    onChange={(event) => setSignature(event.target.value)}
                                />
                                <div className="mt-3 flex justify-end">
                                    <SettingsButton onClick={saveSignature}>Save</SettingsButton>
                                </div>
                            </div>
                        </Section>
                    )}
                    </div>
                </div>
            </div>
        </div>
    );
}
