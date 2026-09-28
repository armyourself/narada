"use client";

import { useEffect, type ReactNode } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { FileSystem } from "@/lib/internal/FileSystem";
import { connectToServer } from "@/lib/internal/Server";
import { PreferenceManager, PreferenceStore, Theme } from "@/lib/preferences";
import { useSharedStore } from "@/lib/stores/shared";
import { useUiStore, close as closeMessage, closeToast, openPalette, openCompose } from "@/lib/stores/ui";
import { local } from "@/lib/locales";
import { DEFAULT_LANGUAGE } from "@/lib/constants";
import { isTauriRuntime, startLocalServer } from "@/lib/server/startLocalServer";
import { Folder, type Account, type Email } from "@/lib/types";
import Loading from "./Loading";
import WindowBar from "./WindowBar";
import ComposeModal from "./ComposeModal";
import CommandPalette from "./CommandPalette";
import ConfirmDialog from "./ConfirmDialog";
import SettingsModal from "./SettingsModal";

/**
 * Dev-only: `?demo=1` seeds a sample mailbox so the dashboard can be
 * reviewed without a running backend (`next dev` only, never in builds).
 */
function seedDemoData(): void {
    if (
        typeof window === "undefined" ||
        process.env.NODE_ENV !== "development" ||
        !new URLSearchParams(window.location.search).has("demo")
    ) {
        return;
    }

    const account: Account = {
        email_address: "alex@narada.example",
        fullname: "Alex Rivera",
        avatar: { bg: "#2383e2", fg: "#ffffff", initials: "AR" },
    };

    const now = Date.now();
    const mail = (
        uid: number,
        sender: string,
        subject: string,
        hoursAgo: number,
        seen: boolean,
        body: string,
    ): Email => ({
        message_id: `<${uid}.demo@narada.example>`,
        uid: String(uid),
        sender,
        receivers: "alex@narada.example",
        date: new Date(now - hoursAgo * 3600 * 1000).toISOString(),
        subject,
        body,
        flags: seen ? ["\\Seen"] : [],
    });

    const emails: Email[] = [
        mail(24, "Notion <release@notion.so>", "Narada 0.4 — Nostr transport notes", 1, false, "<p>Signed relays, NIP-04 downgrade path, and a redesigned mailbox cache. Full notes and migration guide inside...</p>"),
        mail(23, "Maya Chen <maya@quietlab.dev>", "Re: Relay latency benchmarks", 3, false, "<p>Numbers from the Singapore region look great — p95 dropped to 41ms after the pool change. Can you re-run Europe?</p>"),
        mail(22, "GitHub <notifications@github.com>", "[narada] Pipeline green on main", 6, false, "<p>All 141 tests passed in 3m 12s. Artifacts are attached to the run for inspection...</p>"),
        mail(21, "Sam Okafor <sam@meridian.io>", "Q3 security review checklist", 27, true, "<p>Key rotation, threat model refresh, and the dependency audit are still open. Proposed slots next week?</p>"),
        mail(20, "Nostr Relay <ops@damus.net>", "Relay maintenance window", 30, true, "<p>We will restart the eu-1 relay Saturday 02:00 UTC. Expect brief reconnects during the window...</p>"),
        mail(19, "Priya Nair <priya@brightpath.org>", "Offsite agenda + notes", 50, true, "<p>Draft agenda attached — day one is roadmap, day two is the security deep dive. Feedback welcome...</p>"),
        mail(18, "Buildkite <builds@buildkite.com>", "Deploy #1842 succeeded", 74, true, "<p>Deploy #1842 to staging completed successfully in 4m 09s. View the pipeline for details...</p>"),
        mail(17, "Lena Fischer <lena@halcyon.dev>", "Re: Key rotation plan", 96, true, "<p>The staged rollout plan looks right. Let's keep a 7 day overlap for old keys to be safe...</p>"),
    ];

    useSharedStore.setState({
        server: "http://127.0.0.1:8000",
        accounts: [account],
        currentAccount: account,
        failedAccounts: [],
        mailboxes: {
            [account.email_address]: {
                total: emails.length,
                folder: Folder.Inbox,
                emails: { prev: [], current: emails, next: [] },
            },
        },
    });
}

function MessageViewport() {
    const message = useUiStore((s) => s.message);
    if (!message) return null;

    return (
        <div className="modal message">
            <div className="message-card">
                <h3>{message.title}</h3>
                {message.details && <p dangerouslySetInnerHTML={{ __html: message.details }} />}
                <button
                    type="button"
                    className="btn btn-outline"
                    onClick={() => void closeMessage()}
                >
                    {message.onCloseText || local.close[DEFAULT_LANGUAGE]}
                </button>
            </div>
        </div>
    );
}

function ComposeViewport() {
    const compose = useUiStore((s) => s.compose);
    if (!compose) return null;
    return <ComposeModal to={compose.to} subject={compose.subject} body={compose.body} />;
}

function PaletteViewport() {
    const paletteOpen = useUiStore((s) => s.paletteOpen);
    if (!paletteOpen) return null;
    return <CommandPalette />;
}

function SettingsViewport() {
    const settingsOpen = useUiStore((s) => s.settingsOpen);
    if (!settingsOpen) return null;
    return <SettingsModal />;
}

function ToastViewport() {
    const toasts = useUiStore((s) => s.toasts);

    return (
        <>
            {toasts.map((toast) => (
                <div key={toast.id} className="toast">
                    <div className="toast-body" dangerouslySetInnerHTML={{ __html: toast.content }} />
                    <div className="toast-footer">
                        {toast.onUndo && (
                            <button
                                type="button"
                                className="btn btn-outline toast-close"
                                onClick={() => {
                                    void toast.onUndo?.();
                                    closeToast(toast.id);
                                }}
                            >
                                {local.undo[DEFAULT_LANGUAGE]}
                            </button>
                        )}
                        <button
                            type="button"
                            className="btn btn-inline toast-close"
                            onClick={() => closeToast(toast.id)}
                        >
                            X
                        </button>
                    </div>
                </div>
            ))}
        </>
    );
}

/** Boot runs exactly once per page load — React StrictMode invokes effects twice. */
let bootPromise: Promise<void> | null = null;

function boot(): Promise<void> {
    if (!bootPromise) {
        bootPromise = (async () => {
            try {
                seedDemoData();
                // Dev-only screenshot hooks: `?compose=1`, `?palette=1`, `?confirm=1`.
                if (process.env.NODE_ENV === "development") {
                    const devParams = new URLSearchParams(window.location.search);
                    if (devParams.has("compose")) {
                        useUiStore.setState({ compose: {} });
                    }
                    if (devParams.has("palette")) {
                        useUiStore.setState({ paletteOpen: true });
                    }
                    if (devParams.has("confirm")) {
                        useUiStore.setState({
                            confirm: {
                                title: "Delete this conversation?",
                                details: "This conversation will be moved to Trash.",
                                confirmText: "Delete",
                                onConfirm: () => {},
                                onCancel: () => {},
                            },
                        });
                    }
                }
                const fileSystem = await FileSystem.getInstance();
                const savedPreferences = await fileSystem.readPreferences();
                PreferenceManager.init(savedPreferences);

                const savedURL = PreferenceStore.serverURL;
                let connected = await connectToServer(savedURL);
                if (
                    !connected &&
                    isTauriRuntime() &&
                    /^https?:\/\/(127\.0\.0\.1|localhost)(:|\/|$)/.test(savedURL)
                ) {
                    // Saved local server is down (e.g. spawned instance died) — start it again.
                    console.warn("Saved local server is down, starting it:", savedURL);
                    const started = await startLocalServer();
                    if (started.ok) {
                        await PreferenceManager.changeServerURL(started.url, false);
                        await PreferenceManager.savePreferences();
                        connected = await connectToServer(started.url);
                    } else {
                        console.error("Could not restart local server:", started.error);
                    }
                }
                if (!connected && savedURL) console.warn("Could not connect to server", savedURL);
            } catch (error) {
                console.error("Application boot failed", error);
            }
            useSharedStore.setState({ isAppLoaded: true });
        })();
    }
    return bootPromise;
}

export default function Shell({ children }: { children: ReactNode }) {
    const isAppLoaded = useSharedStore((s) => s.isAppLoaded);

    useEffect(() => {
        void boot();
    }, []);

    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            const target = event.target as HTMLElement | null;
            const typing =
                !!target &&
                (target.tagName === "INPUT" ||
                    target.tagName === "TEXTAREA" ||
                    target.isContentEditable);
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
                event.preventDefault();
                openPalette();
                return;
            }
            if (
                !typing &&
                !event.ctrlKey &&
                !event.metaKey &&
                !event.altKey &&
                event.key.toLowerCase() === "n"
            ) {
                openCompose();
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, []);

    useEffect(() => {
        let disposed = false;
        let unlisten: (() => void) | null = null;

        const onThemeChanged = async ({ payload: theme }: { payload: string }) => {
            if (PreferenceStore.theme === Theme.System || !PreferenceStore.theme) {
                const newTheme = theme.toLowerCase();
                document.documentElement.setAttribute("data-color-scheme", newTheme);
                document.documentElement.classList.toggle("dark", newTheme === "dark");
                localStorage.setItem("theme", newTheme);
            }
        };

        try {
            getCurrentWindow()
                .onThemeChanged(onThemeChanged)
                .then((fn) => {
                    if (disposed) fn();
                    else unlisten = fn;
                })
                .catch((err) => console.error("theme listener failed:", err));
        } catch {
            /* Not running inside Tauri */
        }

        return () => {
            disposed = true;
            unlisten?.();
        };
    }, []);

    return (
        <>
            <div className="window-frame">
                <WindowBar />
                <div className="layout-container">
                    {isAppLoaded ? children : <Loading />}
                </div>
            </div>
            <div className="modal-container" id="modal-container">
                <MessageViewport />
                <ConfirmDialog />
                <ComposeViewport />
                <SettingsViewport />
            </div>
            <PaletteViewport />
            <div className="toast-container" id="toast-container">
                <ToastViewport />
            </div>
        </>
    );
}
