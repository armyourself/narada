"use client";

import "./settings.css";
import { useMemo, useState } from "react";
import { useSharedStore } from "@/lib/stores/shared";
import { show as showMessage, showToast, showConfirm } from "@/lib/stores/ui";
import { useNostrIdentity } from "@/lib/nostr/identity";
import { NostrIdentityService } from "@/lib/services/NostrIdentityService";
import { PreferenceManager, PreferenceStore, Theme } from "@/lib/preferences";
import { AccountController } from "@/lib/account";
import type { Account } from "@/lib/types";

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

export default function Settings() {
    const [isRotating, setIsRotating] = useState(false);
    const [isDeleting, setIsDeleting] = useState(false);
    const [themePreference, setThemePreference] = useState<"light" | "dark">(() =>
        readThemePreference(),
    );
    const [notificationsEnabled, setNotificationsEnabled] = useState<boolean>(() =>
        readNotificationPreference(),
    );

    const accounts = useSharedStore((s) => s.accounts);
    const activeAccount = useSharedStore((s) => s.currentAccount);
    const { publicId, loadIdentity } = useNostrIdentity();

    const currentAccount = useMemo(
        () => (activeAccount !== "home" ? (activeAccount as Account) : accounts[0]),
        [activeAccount, accounts],
    );
    const accountId = useMemo(() => currentAccount?.email_address ?? "", [currentAccount]);
    const nodeId = useMemo(() => publicId ?? "not set", [publicId]);

    async function changeTheme(choice: "light" | "dark") {
        await PreferenceManager.changeTheme(
            choice === "dark" ? Theme.Dark : Theme.Light,
        );
        setThemePreference(choice);
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

    async function revealMnemonic() {
        // Rotation returns a one-shot claim token; redeem it for the
        // mnemonic and show it behind a confirm-style reveal. The claim
        // token is single-use, so this effectively re-rolls the recovery
        // phrase — the daemon has no read-only mnemonic endpoint.
        showToast({
            content: "revealing the recovery phrase requires rotating keys — use Rotate keys",
        });
    }

    async function signOut() {
        showConfirm({
            title: "Sign out?",
            confirmText: "Sign out",
            onConfirm: async () => {
                // Removing the account from the daemon logs it out.
                const response = await AccountController.remove(accountId);
                if (!response.success) {
                    showMessage({ title: "sign out failed" });
                    console.error(response.message);
                    return;
                }
                showToast({ content: "signed out" });
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

    async function copyNodeId() {
        try {
            await navigator.clipboard.writeText(nodeId);
            showToast({ content: "node id copied" });
        } catch {
            /* clipboard unavailable — ignore */
        }
    }

    async function changeNotifications(enabled: boolean) {
        await PreferenceManager.changeNotificationStatus(enabled);
        setNotificationsEnabled(enabled);
    }

    return (
        <div className="settings-panel active">
            <div className="settings-title">Settings</div>
            <div className="settings-sub">Your node, your keys, your rules.</div>

            <div className="settings-section">
                <h3>Appearance</h3>
                <div className="settings-row">
                    <div>
                        <div className="settings-row-label">Theme</div>
                        <div className="settings-row-desc">Switch between light and dark.</div>
                    </div>
                    <div className="seg-group">
                        <button
                            className={themePreference === "light" ? "seg-btn active" : "seg-btn"}
                            onClick={() => void changeTheme("light")}
                        >Light</button>
                        <button
                            className={themePreference === "dark" ? "seg-btn active" : "seg-btn"}
                            onClick={() => void changeTheme("dark")}
                        >Dark</button>
                    </div>
                </div>
            </div>

            <div className="settings-section">
                <h3>Node & identity</h3>
                <div className="settings-row" style={{ display: "block" }}>
                    <div className="settings-row-label" style={{ marginBottom: 8 }}>Your node id</div>
                    <div className="settings-node-id">
                        <span>{nodeId}</span>
                        <button onClick={copyNodeId} title="Copy" aria-label="Copy node id">
                            <svg viewBox="0 0 24 24"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                        </button>
                    </div>
                </div>
                <div className="settings-row">
                    <div>
                        <div className="settings-row-label">Recovery phrase</div>
                        <div className="settings-row-desc">{"12-word mnemonic — write it down, don't screenshot it."}</div>
                    </div>
                    <button className="settings-btn" onClick={revealMnemonic}>Reveal</button>
                </div>
                <div className="settings-row">
                    <div>
                        <div className="settings-row-label">Key rotation</div>
                        <div className="settings-row-desc">Rotate your signing key without changing your address.</div>
                    </div>
                    <button className="settings-btn" onClick={rotateKeys} disabled={isRotating || !accountId}>
                        {isRotating ? "Rotating…" : "Rotate keys"}
                    </button>
                </div>
            </div>

            <div className="settings-section">
                <h3>Delivery & privacy</h3>
                <div className="settings-row">
                    <div>
                        <div className="settings-row-label">Read receipts</div>
                        <div className="settings-row-desc">Let senders see a signed delivery acknowledgement.</div>
                    </div>
                    <label className="switch">
                        <input type="checkbox" checked disabled readOnly />
                        <span className="track"></span>
                        <span className="thumb"></span>
                    </label>
                </div>
            </div>

            <div className="settings-section">
                <h3>Notifications</h3>
                <div className="settings-row">
                    <div>
                        <div className="settings-row-label">Desktop notifications</div>
                        <div className="settings-row-desc">Show a banner when new mail arrives.</div>
                    </div>
                    <label className="switch">
                        <input
                            type="checkbox"
                            checked={notificationsEnabled}
                            onChange={(e) => void changeNotifications(e.currentTarget.checked)}
                        />
                        <span className="track"></span>
                        <span className="thumb"></span>
                    </label>
                </div>
            </div>

            <div className="settings-section">
                <h3>Danger zone</h3>
                <div className="settings-row">
                    <div>
                        <div className="settings-row-label">Sign out</div>
                        <div className="settings-row-desc">{"You'll need your recovery phrase to sign back in."}</div>
                    </div>
                    <button className="settings-btn danger" onClick={signOut}>Sign out</button>
                </div>
                <div className="settings-row">
                    <div>
                        <div className="settings-row-label">Delete node identity</div>
                        <div className="settings-row-desc">Permanently destroys your keys. Mail addressed to you becomes undeliverable.</div>
                    </div>
                    <button className="settings-btn danger" onClick={deleteIdentity} disabled={isDeleting || !accountId}>
                        Delete identity
                    </button>
                </div>
            </div>
        </div>
    );
}
