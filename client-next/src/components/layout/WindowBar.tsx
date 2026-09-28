"use client";

import { getCurrentWindow } from "@tauri-apps/api/window";

export default function WindowBar() {
    const run = (action: "minimize" | "toggleMaximize" | "close") => {
        try {
            void getCurrentWindow()[action]();
        } catch (err) {
            /* browser dev: mock is bundled and this is not a Tauri window */
            console.error(`window ${action} failed:`, err);
        }
    };

    return (
        <header className="window-bar" data-tauri-drag-region="deep">
            <div className="window-bar-lights">
                <button
                    type="button"
                    className="window-light window-light-close"
                    aria-label="Close"
                    title="Close"
                    onClick={() => run("close")}
                >
                    <svg viewBox="0 0 24 24">
                        <path d="M7 7l10 10M17 7 7 17" />
                    </svg>
                </button>
                <button
                    type="button"
                    className="window-light window-light-minimize"
                    aria-label="Minimize"
                    title="Minimize"
                    onClick={() => run("minimize")}
                >
                    <svg viewBox="0 0 24 24">
                        <path d="M6 12h12" />
                    </svg>
                </button>
                <button
                    type="button"
                    className="window-light window-light-maximize"
                    aria-label="Maximize"
                    title="Maximize"
                    onClick={() => run("toggleMaximize")}
                >
                    <svg viewBox="0 0 24 24">
                        <path d="M8 16 16 8M10 8h6v6" />
                    </svg>
                </button>
            </div>
            <span className="window-bar-brand">Narada</span>
        </header>
    );
}
