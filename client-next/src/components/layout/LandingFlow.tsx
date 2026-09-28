"use client";

import { useEffect, useState, type FormEvent } from "react";
import Landing from "@/components/layout/Landing";
import { PreferenceManager, PreferenceStore, Language, Theme } from "@/lib/preferences";
import { useSharedStore } from "@/lib/stores/shared";
import { show as showMessage, showToast } from "@/lib/stores/ui";
import { MailboxController } from "@/lib/mailbox";
import { AccountController } from "@/lib/account";
import { NotificationHandler } from "@/lib/notifications";
import { local } from "@/lib/locales";
import { DEFAULT_LANGUAGE, DEFAULT_SERVER_URL } from "@/lib/constants";
import { isTauriRuntime, startLocalServer } from "@/lib/server/startLocalServer";
import { nostrIdentity } from "@/lib/nostr/identity";
import { NostrIdentityService } from "@/lib/services/NostrIdentityService";

type Section = "setup" | "welcome" | "identity" | "accounts";

function SetupServer({ onContinue }: { onContinue: () => void }) {
    const [starting, setStarting] = useState(false);
    const [canStartLocal, setCanStartLocal] = useState(false);

    useEffect(() => {
        showToast({ content: "You can change this later." });
        // eslint-disable-next-line react-hooks/set-state-in-effect -- Tauri runtime flag is only readable after mount
        setCanStartLocal(isTauriRuntime());
    }, []);

    const changeServerURL = async (e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const formData = new FormData(e.currentTarget);
        const targetServerURL = String(formData.get("server_url") ?? "");
        const response = await PreferenceManager.changeServerURL(targetServerURL);

        if (!response) {
            showMessage({ title: local.error_change_server_url[DEFAULT_LANGUAGE] });
            console.error("Could not connect to the target server ", targetServerURL);
        } else {
            await PreferenceManager.savePreferences();
            onContinue();
        }
    };

    const handleStartLocal = async () => {
        if (starting) return;
        setStarting(true);
        try {
            const result = await startLocalServer();
            if (!result.ok) {
                console.error("Could not start the local server:", result.error);
                showMessage({ title: local.error_change_server_url[DEFAULT_LANGUAGE] });
                return;
            }
            const response = await PreferenceManager.changeServerURL(result.url);
            if (!response) {
                console.error("Could not connect to the local server ", result.url);
                showMessage({ title: local.error_change_server_url[DEFAULT_LANGUAGE] });
                return;
            }
            await PreferenceManager.savePreferences();
            onContinue();
        } finally {
            setStarting(false);
        }
    };

    return (
        <form className="form" onSubmit={changeServerURL}>
            <div className="form-group form-group-vertical">
                <label className="label" htmlFor="server_url">
                    {local.server_url[DEFAULT_LANGUAGE]}
                </label>
                <input
                    className="input"
                    type="url"
                    name="server_url"
                    id="server_url"
                    placeholder={local.server_url_example[DEFAULT_LANGUAGE]}
                    defaultValue={DEFAULT_SERVER_URL}
                    autoComplete="off"
                     
                    autoFocus
                    required
                />
            </div>

            <div className="landing-body-footer">
                <button type="submit" className="btn btn-cta">Continue</button>
                {canStartLocal && (
                    <button
                        type="button"
                        className="btn btn-inline"
                        disabled={starting}
                        onClick={() => void handleStartLocal()}
                    >
                        {starting ? "Starting server..." : "Start local server"}
                    </button>
                )}
            </div>
        </form>
    );
}

function Welcome({ onContinue }: { onContinue: () => void }) {
    useEffect(() => {
        showToast({ content: "You can change these later." });
    }, []);

    const saveInitialPreferences = async (e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        await PreferenceManager.savePreferences();
        onContinue();
    };

    return (
        <form className="form" onSubmit={saveInitialPreferences}>
            <div className="form-group form-group-vertical">
                <label className="label" htmlFor="language">Language</label>
                <select
                    className="input"
                    id="language"
                    value={PreferenceStore.language}
                    onChange={(e) => void PreferenceManager.changeLanguage(e.target.value as Language)}
                >
                    {Object.values(Language).map((language) => (
                        <option key={language} value={language}>{language}</option>
                    ))}
                </select>
            </div>

            <div className="form-group form-group-vertical">
                <label className="label" htmlFor="theme">Theme</label>
                <select
                    className="input"
                    id="theme"
                    value={PreferenceStore.theme}
                    onChange={(e) => void PreferenceManager.changeTheme(e.target.value as Theme)}
                >
                    {Object.values(Theme).map((theme) => (
                        <option key={theme} value={theme}>{theme}</option>
                    ))}
                </select>
            </div>

            <div className="landing-body-footer">
                <button type="submit" className="btn btn-cta">Continue</button>
            </div>
        </form>
    );
}

let autoInitMailboxesPromise: Promise<void> | null = null;

type IdentityMode = "generate" | "mnemonic" | "recover";

function IdentitySection({ onContinue }: { onContinue: () => void }) {
    const accounts = useSharedStore((s) => s.accounts);
    const defaultAccountId = accounts[0]?.email_address ?? "";
    const [mode, setMode] = useState<IdentityMode>("generate");
    const [busy, setBusy] = useState(false);
    const [publicId, setPublicId] = useState<string | null>(null);
    const [mnemonic, setMnemonic] = useState<string | null>(null);
    const [mnemonicError, setMnemonicError] = useState<string | null>(null);
    const [copied, setCopied] = useState(false);

    const handleGenerate = async (e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        if (busy) return;
        const formData = new FormData(e.currentTarget);
        const accountId = String(formData.get("account_id") ?? "").trim();
        if (!accountId) {
            showMessage({ title: "Please enter an account ID." });
            return;
        }
        setBusy(true);
        try {
            const result = await nostrIdentity.generateIdentity(accountId);
            if (!result) {
                showMessage({
                    title: "Failed to generate identity. It may already exist.",
                });
                return;
            }
            setPublicId(result.publicId);
            setMnemonic(null);
            setMnemonicError(null);
            const claim = await NostrIdentityService.claimMnemonic(
                accountId,
                result.mnemonicToken,
            );
            if (claim?.mnemonic) setMnemonic(claim.mnemonic);
            else setMnemonicError("Mnemonic could not be retrieved. The token may have expired.");
            setMode("mnemonic");
        } catch {
            showMessage({ title: "Connection error. Is the server running?" });
        } finally {
            setBusy(false);
        }
    };

    const handleRecover = async (e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        if (busy) return;
        const formData = new FormData(e.currentTarget);
        const accountId = String(formData.get("account_id") ?? "").trim();
        const phrase = String(formData.get("mnemonic") ?? "").trim();
        if (!accountId) {
            showMessage({ title: "Please enter an account ID." });
            return;
        }
        if (!phrase) {
            showMessage({ title: "Please enter your recovery mnemonic." });
            return;
        }
        setBusy(true);
        try {
            const recovered = await nostrIdentity.recoverIdentity(accountId, phrase);
            if (recovered) {
                showToast({ content: "Identity recovered" });
                onContinue();
            } else {
                showMessage({
                    title: "Recovery failed. Check your mnemonic and try again.",
                });
            }
        } catch {
            showMessage({ title: "Connection error. Is the server running?" });
        } finally {
            setBusy(false);
        }
    };

    const copyMnemonic = async () => {
        if (!mnemonic) return;
        try {
            await navigator.clipboard.writeText(mnemonic);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            /* clipboard unavailable — select-to-copy still works */
        }
    };

    if (mode === "mnemonic") {
        return (
            <div className="flex flex-col gap-5">
                <div className="text-center">
                    <h3 className="text-base font-semibold text-notion-text mb-2">
                        Your Nostr Identity
                    </h3>
                    <p className="text-xs text-notion-text-secondary mb-1">Public ID</p>
                    <code className="block p-2 bg-notion-surface-sunken rounded text-xs break-all font-mono text-notion-text">
                        {publicId}
                    </code>
                </div>

                <div className="text-center">
                    <h4 className="text-sm font-medium text-notion-text mb-2">
                        Recovery Mnemonic
                    </h4>
                    {mnemonicError ? (
                        <p className="text-xs text-notion-danger">{mnemonicError}</p>
                    ) : mnemonic ? (
                        <>
                            <div className="p-2.5 mb-2 border border-dashed border-notion-border rounded bg-notion-surface-sunken">
                                <code className="text-sm break-words font-mono text-notion-text select-all">
                                    {mnemonic}
                                </code>
                            </div>
                            <button type="button" className="btn btn-outline" onClick={() => void copyMnemonic()}>
                                {copied ? "Copied!" : "Copy to clipboard"}
                            </button>
                        </>
                    ) : (
                        <p className="text-xs text-notion-text-secondary">Loading mnemonic…</p>
                    )}
                </div>

                <div className="p-2.5 border border-notion-border rounded bg-notion-surface-sunken text-xs text-notion-text-secondary text-center">
                    <strong className="text-notion-text">Write this down!</strong>{" "}
                    This is the only way to recover your identity. If you lose it,
                    your identity cannot be restored.
                </div>

                <div className="landing-body-footer">
                    <button type="button" className="btn btn-cta" onClick={onContinue}>
                        I have saved my mnemonic
                    </button>
                </div>
            </div>
        );
    }

    if (mode === "recover") {
        return (
            <form className="form" onSubmit={handleRecover}>
                <div className="form-group form-group-vertical">
                    <label className="label" htmlFor="recovery_account_id">Account ID</label>
                    <input
                        className="input"
                        type="text"
                        name="account_id"
                        id="recovery_account_id"
                        placeholder="e.g. alice@example.com"
                        defaultValue={defaultAccountId}
                        autoComplete="off"
                        autoFocus
                        required
                    />
                </div>
                <div className="form-group form-group-vertical">
                    <label className="label" htmlFor="mnemonic">Recovery Mnemonic</label>
                    <input
                        className="input"
                        type="text"
                        name="mnemonic"
                        id="mnemonic"
                        placeholder="Enter your 12-word recovery phrase"
                        autoComplete="off"
                        required
                    />
                    <span className="text-xs text-notion-text-secondary">
                        Enter the mnemonic you saved when generating your identity.
                    </span>
                </div>
                <div className="landing-body-footer">
                    <button type="submit" className="btn btn-cta" disabled={busy}>
                        {busy ? "Recovering…" : "Recover Identity"}
                    </button>
                    <button
                        type="button"
                        className="btn btn-inline"
                        onClick={() => setMode("generate")}
                    >
                        Back to generate
                    </button>
                </div>
            </form>
        );
    }

    return (
        <form className="form" onSubmit={handleGenerate}>
            <div className="form-group form-group-vertical">
                <label className="label" htmlFor="identity_account_id">Account ID</label>
                <input
                    className="input"
                    type="text"
                    name="account_id"
                    id="identity_account_id"
                    placeholder="e.g. alice@example.com"
                    defaultValue={defaultAccountId}
                    autoComplete="off"
                    autoFocus
                    required
                />
                <span className="text-xs text-notion-text-secondary">
                    Your Nostr identity will be tied to this account.
                </span>
            </div>
            <div className="landing-body-footer">
                <button type="submit" className="btn btn-cta" disabled={busy}>
                    {busy ? "Generating…" : "Generate Identity"}
                </button>
                <button
                    type="button"
                    className="btn btn-inline"
                    onClick={() => setMode("recover")}
                >
                    Recover from mnemonic
                </button>
                <button type="button" className="btn btn-inline" onClick={onContinue}>
                    Skip for now
                </button>
            </div>
        </form>
    );
}


function AccountsSection() {
    const accounts = useSharedStore((s) => s.accounts);
    const failedAccounts = useSharedStore((s) => s.failedAccounts);
    const server = useSharedStore((s) => s.server);
    const listedAccounts = [...failedAccounts, ...accounts];
    const [showAddForm, setShowAddForm] = useState(
        () =>
            process.env.NODE_ENV === "development" &&
            typeof window !== "undefined" &&
            new URLSearchParams(window.location.search).get("accountForm") === "1",
    );
    const [showPassword, setShowPassword] = useState(false);

    useEffect(() => {
        if (failedAccounts.length > 0) {
            showToast({ content: local.accounts_failed_to_connect[DEFAULT_LANGUAGE] });
        } else if (accounts.length === 0) {
            showToast({ content: "You havent add any account." });
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const initMailboxes = async () => {
        const response = await MailboxController.init();
        if (!response.success) {
            showMessage({ title: local.error_initialize_mailboxes[DEFAULT_LANGUAGE], details: response.message });
            return;
        }
        try {
            accounts.forEach((account) => new NotificationHandler(account));
        } catch (error) {
            console.error("Notifications could not be initialized", error);
        }
    };

    useEffect(() => {
        // Auto-continue into the mailbox as soon as accounts + server are
        // known, so users never wait for a manual click. The "Continue to
        // mailbox" button stays as a fallback (e.g. after a failed attempt).
        if (accounts.length === 0 || !server || autoInitMailboxesPromise) return;
        autoInitMailboxesPromise = initMailboxes();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [accounts.length, server]);

    const addAccount = async (e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const formData = new FormData(e.currentTarget);
        const response = await AccountController.add(
            String(formData.get("email_address") ?? ""),
            String(formData.get("password") ?? ""),
            String(formData.get("fullname") ?? "") || null,
        );

        if (!response.success) {
            showMessage({ title: local.error_add_account[DEFAULT_LANGUAGE], details: response.message });
            return;
        }
        setShowAddForm(false);
    };

    if (showAddForm) {
        return (
            <form className="form" onSubmit={addAccount}>
                <div className="form-group form-group-vertical">
                    <label className="label" htmlFor="email_address">
                        {local.email_address[DEFAULT_LANGUAGE]}
                    </label>
                    <input
                        className="input"
                        type="email"
                        name="email_address"
                        id="email_address"
                        placeholder={local.email_address_example[DEFAULT_LANGUAGE]}
                        autoComplete="off"
                        autoFocus
                        required
                    />
                </div>

                <div className="form-group form-group-vertical">
                    <label className="label" htmlFor="password">
                        {local.password[DEFAULT_LANGUAGE]}
                    </label>
                    <div className="flex items-center border border-notion-border rounded-md bg-notion-surface px-1 focus-within:border-notion-accent transition-colors">
                        <input
                            className="flex-1 min-w-0 bg-transparent border-none px-3 py-2 text-sm text-notion-text outline-none"
                            type={showPassword ? "text" : "password"}
                            name="password"
                            id="password"
                            placeholder={local.password[DEFAULT_LANGUAGE]}
                            autoComplete="new-password"
                            required
                        />
                        <button
                            type="button"
                            aria-label={showPassword ? "Hide password" : "Show password"}
                            onClick={() => setShowPassword((visible) => !visible)}
                            className="flex items-center justify-center w-8 h-8 text-notion-text-muted hover:text-notion-text transition-colors"
                        >
                            {showPassword ? (
                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" className="w-4 h-4" fill="currentColor" aria-hidden="true">
                                    <path d="M228,175a8,8,0,0,1-10.92-3l-19-33.2A123.23,123.23,0,0,1,162,155.46l5.87,35.22a8,8,0,0,1-6.58,9.21A8.4,8.4,0,0,1,160,200a8,8,0,0,1-7.88-6.69l-5.77-34.58a133.06,133.06,0,0,1-36.68,0l-5.77,34.58A8,8,0,0,1,96,200a8.4,8.4,0,0,1-1.32-.11,8,8,0,0,1-6.58-9.21L94,155.46a123.23,123.23,0,0,1-36.06-16.69L39,172A8,8,0,1,1,25.06,164l20-35a153.47,153.47,0,0,1-19.3-20A8,8,0,1,1,38.22,99c16.6,20.54,45.64,45,89.78,45s73.18-24.49,89.78-45A8,8,0,1,1,230.22,109a153.47,153.47,0,0,1-19.3,20l20,35A8,8,0,0,1,228,175Z" />
                                </svg>
                            ) : (
                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" className="w-4 h-4" fill="currentColor" aria-hidden="true">
                                    <path d="M247.31,124.76c-.35-.79-8.82-19.58-27.65-38.41C194.57,61.26,162.88,48,128,48S61.43,61.26,36.34,86.35C17.51,105.18,9,124,8.69,124.76a8,8,0,0,0,0,6.5c.35.79,8.82,19.57,27.65,38.4C61.43,194.74,93.12,208,128,208s66.57-13.26,91.66-38.34c18.83-18.83,27.3-37.61,27.65-38.4A8,8,0,0,0,247.31,124.76ZM128,192c-30.78,0-57.67-11.19-79.93-33.25A133.47,133.47,0,0,1,25,128,133.33,133.33,0,0,1,48.07,97.25C70.33,75.19,97.22,64,128,64s57.67,11.19,79.93,33.25A133.46,133.46,0,0,1,231.05,128C223.84,141.46,192.43,192,128,192Zm0-112a48,48,0,1,0,48,48A48.05,48.05,0,0,0,128,80Zm0,80a32,32,0,1,1,32-32A32,32,0,0,1,128,160Z" />
                                </svg>
                            )}
                        </button>
                    </div>
                </div>

                <div className="form-group form-group-vertical">
                    <label className="label" htmlFor="fullname">
                        {local.full_name_optional[DEFAULT_LANGUAGE]}
                    </label>
                    <input
                        className="input"
                        type="text"
                        name="fullname"
                        id="fullname"
                        placeholder={local.full_name_placeholder[DEFAULT_LANGUAGE]}
                        autoComplete="off"
                    />
                    <span className="text-xs text-notion-text-secondary">
                        {local.full_name_example[DEFAULT_LANGUAGE]}
                    </span>
                </div>

                <div className="landing-body-footer">
                    <button type="submit" className="btn btn-cta">
                        {local.connect_to_account[DEFAULT_LANGUAGE]}
                    </button>
                    <button
                        type="button"
                        className="btn btn-inline"
                        onClick={() => setShowAddForm(false)}
                    >
                        {local.which_accounts_added[DEFAULT_LANGUAGE]}
                    </button>
                </div>
            </form>
        );
    }

    return (
        <div>
            {accounts.length === 0 && failedAccounts.length === 0 ? (
                <button
                    type="button"
                    className="btn btn-cta"
                    onClick={() => setShowAddForm(true)}
                >
                    Add an account
                </button>
            ) : (
                <>
                    <div className="border border-notion-border rounded-md divide-y divide-notion-border overflow-hidden">
                        {listedAccounts.map((account) => {
                            const isFailed = failedAccounts.some(
                                (failed) =>
                                    failed.email_address === account.email_address,
                            );
                            return (
                                <div
                                    key={account.email_address}
                                    className={`flex items-center justify-between gap-3 px-3 py-2.5 text-sm${isFailed ? " bg-notion-danger/5" : ""}`}
                                >
                                    <div className="flex items-center space-x-3 min-w-0">
                                        <div
                                            className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold flex-shrink-0 ${isFailed ? "bg-notion-warning/15 text-notion-warning" : "bg-notion-accent-tint text-notion-accent"}`}
                                        >
                                            {(account.fullname || account.email_address)[0].toUpperCase()}
                                        </div>
                                        <div className="min-w-0">
                                            <div className="font-medium text-notion-text truncate">
                                                {account.fullname || account.email_address}
                                            </div>
                                            <div className="text-xs text-notion-text-muted truncate">
                                                {account.email_address}
                                            </div>
                                        </div>
                                    </div>
                                    {isFailed && (
                                        <span className="shrink-0 rounded-full bg-notion-warning/15 px-2 py-0.5 text-xs font-medium text-notion-warning">
                                            {local.account_failed_to_connect[DEFAULT_LANGUAGE]}
                                        </span>
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    <div className="landing-body-footer">
                        <button
                            type="button"
                            className="btn btn-cta"
                            disabled={accounts.length === 0}
                            onClick={() => void initMailboxes()}
                        >
                            {local.continue_to_mailbox[DEFAULT_LANGUAGE]}
                        </button>
                        <button
                            type="button"
                            className="btn btn-inline"
                            onClick={() => setShowAddForm(true)}
                        >
                            {local.add_another_account[DEFAULT_LANGUAGE]}
                        </button>
                    </div>
                </>
            )}
        </div>
    );
}

export default function LandingFlow() {
    const accounts = useSharedStore((s) => s.accounts);
    const failedAccounts = useSharedStore((s) => s.failedAccounts);
    const server = useSharedStore((s) => s.server);

    const [section, setSection] = useState<Section>(() => {
        if (
            process.env.NODE_ENV === "development" &&
            typeof window !== "undefined" &&
            new URLSearchParams(window.location.search).get("accountForm") === "1"
        )
            return "accounts";
        if (accounts.length > 0 || failedAccounts.length > 0) return "accounts";
        return server ? "welcome" : "setup";
    });

    return (
        <Landing>
            {section === "setup" && <SetupServer onContinue={() => setSection("welcome")} />}
            {section === "welcome" && (
                <Welcome onContinue={() => setSection("identity")} />
            )}
            {section === "identity" && (
                <IdentitySection onContinue={() => setSection("accounts")} />
            )}
            {section === "accounts" && <AccountsSection />}
        </Landing>
    );
}
