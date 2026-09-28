"use client";

import { useEffect, useState } from "react";
import { useSharedStore } from "@/lib/stores/shared";
import { show as showMessage, showToast, closeCompose, showConfirm } from "@/lib/stores/ui";
import { MailboxController } from "@/lib/mailbox";
import type { Account } from "@/lib/types";

type SendTransport = "auto" | "email" | "nostr";

const TRANSPORT_LABELS: Record<SendTransport, string> = {
    auto: "Smart routing",
    email: "Email (SMTP)",
    nostr: "Nostr",
};

const TRANSPORT_HINTS: Record<SendTransport, string> = {
    auto: "npub → Nostr · email → SMTP",
    email: "Conventional mail only",
    nostr: "Nostr relays only",
};

function isNpubRecipient(value: string): boolean {
    const v = value.trim();
    return v.startsWith("npub1") || /^[0-9a-fA-F]{64}$/.test(v);
}

export default function ComposeModal({
    to = "",
    subject = "",
    body = "",
}: {
    to?: string;
    subject?: string;
    body?: string;
}) {
    const currentAccountState = useSharedStore((s) => s.currentAccount);
    const accounts = useSharedStore((s) => s.accounts);

    const [recipient, setRecipient] = useState(to);
    const [subjectValue, setSubjectValue] = useState(subject);
    const [bodyValue, setBodyValue] = useState(body);
    const [isSending, setIsSending] = useState(false);
    const [transport, setTransport] = useState<SendTransport>("auto");
    const [sendMenuOpen, setSendMenuOpen] = useState(false);

    const currentAccount: Account | undefined =
        currentAccountState !== "home" ? currentAccountState : accounts[0];

    const discard = () => {
        if (recipient.trim() || subjectValue.trim() || bodyValue.trim()) {
            showConfirm({
                title: "Discard this draft?",
                details: "Your message will be lost.",
                confirmText: "Discard",
                onConfirm: () => closeCompose(),
            });
        } else {
            closeCompose();
        }
    };

    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                if (sendMenuOpen) setSendMenuOpen(false);
                else closeCompose();
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [sendMenuOpen]);

    const sendEmail = async () => {
        if (!recipient.trim()) {
            showMessage({ title: "Please specify a recipient." });
            return;
        }
        if (!subjectValue.trim()) {
            showMessage({ title: "Please specify a subject." });
            return;
        }

        const recipients = recipient
            .split(",")
            .map((entry) => entry.trim())
            .filter(Boolean);
        if (transport === "nostr" && recipients.some((entry) => !isNpubRecipient(entry))) {
            showMessage({
                title: "Nostr routing needs npub recipients — use Smart routing, or remove the email addresses.",
            });
            return;
        }
        if (transport === "email" && recipients.some(isNpubRecipient)) {
            showMessage({
                title: "npub recipients can't go over SMTP — use Smart routing or Nostr instead.",
            });
            return;
        }

        setIsSending(true);
        try {
            // One endpoint, chosen transport: "auto" routes each recipient
            // on its own (npub → Nostr, email → SMTP).
            const formData = new FormData();
            formData.set("sender", currentAccount?.email_address || "");
            formData.set("receivers", recipient.trim());
            formData.set("subject", subjectValue.trim());
            formData.set("body", bodyValue.trim());
            formData.set("transport", transport);
            const response = await MailboxController.sendEmail(formData);
            if (response.success) {
                showToast({
                    content:
                        response.message ||
                        `Sent via ${TRANSPORT_LABELS[transport]}`,
                });
                closeCompose();
            } else {
                showMessage({ title: response.message || "Failed to send" });
            }
        } catch (err) {
            showMessage({ title: String(err) });
        } finally {
            setIsSending(false);
            setSendMenuOpen(false);
        }
    };

    const pickTransport = (next: SendTransport) => {
        setTransport(next);
        setSendMenuOpen(false);
    };

    return (
        <div
            className="modal compose fixed inset-0 flex items-center justify-center"
            onClick={closeCompose}
        >
            <div
                className="bg-notion-surface w-full max-w-[600px] rounded-xl shadow-notion-popover border border-notion-border overflow-hidden flex flex-col"
                onClick={(event) => event.stopPropagation()}
            >
                {/* Header */}
                <div className="px-4 py-3 border-b border-notion-border flex items-center justify-between bg-notion-surface-sunken">
                    <span className="text-sm font-semibold text-notion-text">New Message</span>
                    <button
                        type="button"
                        className="text-notion-text-muted hover:text-notion-text"
                        onClick={closeCompose}
                    >
                        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M18 6 6 18" />
                            <path d="m6 6 12 12" />
                        </svg>
                    </button>
                </div>

                {/* Form */}
                <div className="p-4 space-y-3">
                    <div className="flex items-center border-b border-notion-border pb-2">
                        <span className="text-xs text-notion-text-muted w-16">To:</span>
                        <input
                            type="text"
                            value={recipient}
                            placeholder="Recipient email or npub"
                            className="w-full text-sm bg-transparent focus:outline-none text-notion-text placeholder:text-notion-text-muted"
                            onChange={(event) => setRecipient(event.target.value)}
                        />
                    </div>
                    <div className="flex items-center border-b border-notion-border pb-2">
                        <span className="text-xs text-notion-text-muted w-16">Subject:</span>
                        <input
                            type="text"
                            value={subjectValue}
                            placeholder="Email subject"
                            className="w-full text-sm bg-transparent focus:outline-none text-notion-text placeholder:text-notion-text-muted"
                            onChange={(event) => setSubjectValue(event.target.value)}
                        />
                    </div>
                    <textarea
                        value={bodyValue}
                        placeholder="Write your email here..."
                        className="w-full h-48 bg-transparent text-sm focus:outline-none resize-none pt-2 text-notion-text placeholder:text-notion-text-muted"
                        onChange={(event) => setBodyValue(event.target.value)}
                    />
                </div>

                {/* Footer */}
                <div className="px-4 py-3 border-t border-notion-border bg-notion-surface-sunken flex items-center justify-between">
                    <div></div>
                    <div className="flex items-center space-x-2 relative">
                        <button
                            type="button"
                            className="px-3 py-1.5 text-xs text-notion-text-secondary hover:bg-notion-hover rounded transition-colors"
                            onClick={discard}
                        >
                            Discard
                        </button>
                        {/* Split Send: main button sends with the chosen
                            transport, caret opens the transport menu. */}
                        <div className="flex items-stretch rounded overflow-hidden">
                            <button
                                type="button"
                                className="px-4 py-1.5 bg-notion-accent hover:opacity-90 text-white text-xs font-medium transition-opacity flex items-center space-x-1 disabled:opacity-50"
                                onClick={() => void sendEmail()}
                                disabled={isSending}
                            >
                                <span>{isSending ? "Sending..." : "Send"}</span>
                                <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <line x1="22" y1="2" x2="11" y2="13" />
                                    <polygon points="22 2 15 22 11 13 2 9 22 2" />
                                </svg>
                            </button>
                            <button
                                type="button"
                                aria-label="Choose send transport"
                                aria-haspopup="menu"
                                aria-expanded={sendMenuOpen}
                                className="px-1.5 bg-notion-accent hover:opacity-90 text-white border-l border-white/30 disabled:opacity-50 flex items-center"
                                onClick={() => setSendMenuOpen((open) => !open)}
                                disabled={isSending}
                            >
                                <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="m6 9 6 6 6-6" />
                                </svg>
                            </button>
                        </div>
                        {sendMenuOpen && (
                            <>
                                <div
                                    className="fixed inset-0 z-40"
                                    onClick={() => setSendMenuOpen(false)}
                                />
                                <div
                                    role="menu"
                                    className="absolute bottom-full right-0 mb-1.5 w-60 bg-notion-surface border border-notion-border rounded-lg shadow-notion-popover py-1 z-50"
                                >
                                    {(Object.keys(TRANSPORT_LABELS) as SendTransport[]).map(
                                        (mode) => (
                                            <button
                                                key={mode}
                                                type="button"
                                                role="menuitemradio"
                                                aria-checked={transport === mode}
                                                className={`w-full text-left px-3 py-1.5 text-xs flex items-center justify-between hover:bg-notion-hover ${
                                                    transport === mode
                                                        ? "text-notion-accent"
                                                        : "text-notion-text"
                                                }`}
                                                onClick={() => pickTransport(mode)}
                                            >
                                                <span className="flex flex-col gap-0.5">
                                                    <span className="font-medium">
                                                        {TRANSPORT_LABELS[mode]}
                                                    </span>
                                                    <span className="text-notion-text-muted">
                                                        {TRANSPORT_HINTS[mode]}
                                                    </span>
                                                </span>
                                                {transport === mode && (
                                                    <svg
                                                        className="w-3.5 h-3.5 shrink-0"
                                                        viewBox="0 0 24 24"
                                                        fill="none"
                                                        stroke="currentColor"
                                                        strokeWidth="2.5"
                                                    >
                                                        <path d="M20 6 9 17l-5-5" />
                                                    </svg>
                                                )}
                                            </button>
                                        ),
                                    )}
                                </div>
                            </>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
