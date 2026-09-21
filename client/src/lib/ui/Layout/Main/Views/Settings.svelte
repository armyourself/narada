<script lang="ts">
    import { SharedStore } from "$lib/stores/shared.svelte";
    import { PreferenceManager, PreferenceStore, Theme } from "$lib/preferences";
    import { nostrIdentity } from "$lib/nostr/identity.svelte";
    import { NostrIdentityService } from "$lib/services/NostrIdentityService";
    import { show as showConfirm } from "$lib/ui/Components/Confirm";
    import { show as showToast } from "$lib/ui/Components/Toast";
    import { show as showMessage } from "$lib/ui/Components/Message";
    import type { Account } from "$lib/types";

    let isRotating = $state(false);
    let isDeleting = $state(false);

    let currentAccount = $derived(
        SharedStore.currentAccount !== "home"
            ? (SharedStore.currentAccount as Account)
            : SharedStore.accounts[0],
    );

    let accountId = $derived(currentAccount?.email_address ?? "");
    let nodeId = $derived(nostrIdentity.state.publicId ?? "not set");

    let themePreference = $derived(
        PreferenceStore.theme === Theme.Dark ? "dark" : "light",
    );

    async function changeTheme(choice: "light" | "dark") {
        await PreferenceManager.changeTheme(
            choice === "dark" ? Theme.Dark : Theme.Light,
        );
    }

    async function rotateKeys() {
        if (!accountId || isRotating) return;
        isRotating = true;
        try {
            const result = await NostrIdentityService.rotateX25519(accountId);
            if (result) {
                await nostrIdentity.loadIdentity(accountId);
                showToast({ content: "keys rotated" });
            } else {
                showMessage({ title: "key rotation failed" });
            }
        } finally {
            isRotating = false;
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
            onConfirmText: "Sign out",
            onConfirm: async () => {
                // Removing the account from the daemon logs it out.
                const { AccountController } = await import("$lib/account");
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
            onConfirmText: "Delete identity",
            onConfirm: async () => {
                if (!accountId || isDeleting) return;
                isDeleting = true;
                try {
                    const ok = await NostrIdentityService.deleteIdentity(accountId);
                    if (ok) {
                        nostrIdentity.state.publicId = null;
                        showToast({ content: "identity deleted" });
                    } else {
                        showMessage({ title: "identity deletion failed" });
                    }
                } finally {
                    isDeleting = false;
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
    }
</script>

<div class="settings-panel active">
    <div class="settings-title">Settings</div>
    <div class="settings-sub">Your node, your keys, your rules.</div>

    <div class="settings-section">
        <h3>Appearance</h3>
        <div class="settings-row">
            <div>
                <div class="settings-row-label">Theme</div>
                <div class="settings-row-desc">Switch between light and dark.</div>
            </div>
            <div class="seg-group">
                <button
                    class="seg-btn"
                    class:active={themePreference === "light"}
                    onclick={() => changeTheme("light")}
                >Light</button>
                <button
                    class="seg-btn"
                    class:active={themePreference === "dark"}
                    onclick={() => changeTheme("dark")}
                >Dark</button>
            </div>
        </div>
    </div>

    <div class="settings-section">
        <h3>Node &amp; identity</h3>
        <div class="settings-row" style="display:block;">
            <div class="settings-row-label" style="margin-bottom:8px;">Your node id</div>
            <div class="settings-node-id">
                <span>{nodeId}</span>
                <button onclick={copyNodeId} title="Copy" aria-label="Copy node id">
                    <svg viewBox="0 0 24 24"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                </button>
            </div>
        </div>
        <div class="settings-row">
            <div>
                <div class="settings-row-label">Recovery phrase</div>
                <div class="settings-row-desc">12-word mnemonic — write it down, don't screenshot it.</div>
            </div>
            <button class="settings-btn" onclick={revealMnemonic}>Reveal</button>
        </div>
        <div class="settings-row">
            <div>
                <div class="settings-row-label">Key rotation</div>
                <div class="settings-row-desc">Rotate your signing key without changing your address.</div>
            </div>
            <button class="settings-btn" onclick={rotateKeys} disabled={isRotating || !accountId}>
                {isRotating ? "Rotating…" : "Rotate keys"}
            </button>
        </div>
    </div>

    <div class="settings-section">
        <h3>Delivery &amp; privacy</h3>
        <div class="settings-row">
            <div>
                <div class="settings-row-label">Read receipts</div>
                <div class="settings-row-desc">Let senders see a signed delivery acknowledgement.</div>
            </div>
            <label class="switch">
                <input type="checkbox" checked disabled>
                <span class="track"></span>
                <span class="thumb"></span>
            </label>
        </div>
    </div>

    <div class="settings-section">
        <h3>Notifications</h3>
        <div class="settings-row">
            <div>
                <div class="settings-row-label">Desktop notifications</div>
                <div class="settings-row-desc">Show a banner when new mail arrives.</div>
            </div>
            <label class="switch">
                <input
                    type="checkbox"
                    checked={PreferenceStore.notificationStatus !== false}
                    onchange={(e) => changeNotifications((e.currentTarget as HTMLInputElement).checked)}
                >
                <span class="track"></span>
                <span class="thumb"></span>
            </label>
        </div>
    </div>

    <div class="settings-section">
        <h3>Danger zone</h3>
        <div class="settings-row">
            <div>
                <div class="settings-row-label">Sign out</div>
                <div class="settings-row-desc">You'll need your recovery phrase to sign back in.</div>
            </div>
            <button class="settings-btn danger" onclick={signOut}>Sign out</button>
        </div>
        <div class="settings-row">
            <div>
                <div class="settings-row-label">Delete node identity</div>
                <div class="settings-row-desc">Permanently destroys your keys. Mail addressed to you becomes undeliverable.</div>
            </div>
            <button class="settings-btn danger" onclick={deleteIdentity} disabled={isDeleting || !accountId}>
                Delete identity
            </button>
        </div>
    </div>
</div>

<style>
    :global {
        .settings-panel {
            flex-grow: 1;
            display: none;
            flex-direction: column;
            background: var(--cream);
            padding: 32px 44px;
            overflow-y: auto;
            min-width: 0;
        }

        .settings-panel.active {
            display: flex;
        }

        .settings-panel .settings-title {
            font-family: var(--ui);
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 6px;
        }

        .settings-panel .settings-sub {
            font-size: 0.82rem;
            color: var(--ink-faint);
            margin-bottom: 34px;
        }

        .settings-panel .settings-section {
            max-width: 560px;
            margin-bottom: 34px;
            padding-bottom: 34px;
            border-bottom: 1px solid var(--glass-border);
        }

        .settings-panel .settings-section:last-of-type {
            border-bottom: none;
        }

        .settings-panel .settings-section h3 {
            font-family: var(--ui);
            font-size: 0.68rem;
            font-weight: 600;
            color: var(--ink-faint);
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 16px;
        }

        .settings-panel .settings-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            padding: 12px 0;
        }

        .settings-panel .settings-row-label {
            font-size: 0.86rem;
            color: var(--ink);
            font-weight: 500;
        }

        .settings-panel .settings-row-desc {
            font-size: 0.74rem;
            color: var(--ink-faint);
            margin-top: 2px;
        }

        .settings-panel .settings-node-id {
            font-family: var(--ui);
            font-size: 0.78rem;
            color: var(--ink-dim);
            background: var(--glass-strong);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius-sm);
            padding: 11px 14px;
            word-break: break-all;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
        }

        .settings-panel .settings-node-id button {
            color: var(--ink-faint);
            flex-shrink: 0;
        }

        .settings-panel .settings-node-id button:hover {
            color: var(--accent);
        }

        .settings-panel .settings-node-id button svg {
            width: 15px;
            height: 15px;
            stroke: currentColor;
            fill: none;
            stroke-width: 1.9;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        .settings-panel .seg-group {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }

        .settings-panel .seg-btn {
            font-family: var(--ui);
            font-size: 0.78rem;
            color: var(--ink-dim);
            background: var(--glass-strong);
            border: 1px solid var(--glass-border);
            padding: 8px 16px;
            border-radius: 100px;
            transition: background 0.15s, color 0.15s, border-color 0.15s;
        }

        .settings-panel .seg-btn:hover {
            background: var(--glass-solid);
            color: var(--ink);
        }

        .settings-panel .seg-btn.active {
            background: var(--accent);
            border-color: var(--accent);
            color: #fff;
        }

        .settings-panel .switch {
            position: relative;
            width: 38px;
            height: 22px;
            flex-shrink: 0;
            cursor: pointer;
        }

        .settings-panel .switch input {
            opacity: 0;
            width: 0;
            height: 0;
            position: absolute;
        }

        .settings-panel .switch .track {
            position: absolute;
            inset: 0;
            background: var(--glass-border);
            border-radius: 100px;
            transition: background 0.2s ease;
        }

        .settings-panel .switch .thumb {
            position: absolute;
            top: 3px;
            left: 3px;
            width: 16px;
            height: 16px;
            border-radius: 50%;
            background: #fff;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
            transition: transform 0.2s ease;
        }

        .settings-panel .switch input:checked ~ .track {
            background: var(--accent);
        }

        .settings-panel .switch input:checked ~ .thumb {
            transform: translateX(16px);
        }

        .settings-panel .settings-btn {
            font-family: var(--ui);
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--ink);
            background: var(--glass-strong);
            border: 1px solid var(--glass-border);
            padding: 9px 18px;
            border-radius: 100px;
            transition: background 0.15s ease, transform 0.15s ease;
        }

        .settings-panel .settings-btn:hover {
            background: var(--glass-solid);
            transform: translateY(-1px);
        }

        .settings-panel .settings-btn.danger {
            color: #B4553E;
            border-color: rgba(180, 85, 62, 0.35);
            background: rgba(180, 85, 62, 0.08);
        }

        .settings-panel .settings-btn.danger:hover {
            background: rgba(180, 85, 62, 0.15);
        }

        .settings-panel .settings-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
    }
</style>
