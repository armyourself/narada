"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Account, Attachment, Email } from "@/lib/types";
import { extractFullname, extractEmailAddress } from "@/lib/utils";
import { buildEmailSrcDoc, looksLikeHtml } from "@/lib/utils/mailhtml";
import { showToast, openCompose } from "@/lib/stores/ui";
import { MailboxController } from "@/lib/mailbox";
import RouteBadge, { emailDeliveryRoute } from "@/components/views/RouteBadge";

interface Props {
    email: Email;
    account?: Account;
    folder: string;
    onClose: () => void;
}

function Icon({ className, children }: { className?: string; children: React.ReactNode }) {
    return (
        <svg
            className={className ?? "w-5 h-5"}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            {children}
        </svg>
    );
}

function ToolbarButton({
    title,
    onClick,
    children,
}: {
    title: string;
    onClick: () => void;
    children: React.ReactNode;
}) {
    return (
        <button
            type="button"
            title={title}
            className="w-7 h-7 rounded flex items-center justify-center text-[#ffffff71] hover:bg-white/10 hover:text-[#d3d3d3] transition-colors"
            onClick={onClick}
        >
            <Icon>{children}</Icon>
        </button>
    );
}

function comingSoon(feature: string) {
    showToast({ content: `${feature} is being ported.` });
}

// Mockup F2 label chip row: dimmed "Add label" + `#373737` chips with a
// small X. Labels are session-local (keyed by uid in the parent).
function LabelsRow({
    labels,
    onChange,
}: {
    labels: string[];
    onChange: (next: string[]) => void;
}) {
    const [adding, setAdding] = useState(false);
    const [draft, setDraft] = useState("");

    const commit = () => {
        const value = draft.trim();
        if (value && !labels.includes(value)) onChange([...labels, value]);
        setDraft("");
        setAdding(false);
    };

    return (
        <div className="flex items-center gap-2 flex-wrap">
            {adding ? (
                <input
                    autoFocus
                    value={draft}
                    placeholder="Label name"
                    className="h-5 w-28 px-1.5 rounded-[3px] bg-white/5 text-sm font-medium text-[#d3d3d3] outline-none ring-1 ring-[#2383e2]"
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={(event) => {
                        if (event.key === "Enter") commit();
                        if (event.key === "Escape") {
                            setDraft("");
                            setAdding(false);
                        }
                    }}
                    onBlur={commit}
                />
            ) : (
                <button
                    type="button"
                    className="h-5 px-1.5 rounded-[3px] text-sm font-medium text-[#d3d3d3] opacity-50 hover:opacity-100 transition-opacity"
                    onClick={() => setAdding(true)}
                >
                    Add label
                </button>
            )}
            {labels.map((label) => (
                <span
                    key={label}
                    className="group flex items-center gap-1 h-5 px-1.5 rounded-[3px] bg-[#373737] text-sm font-medium text-[#d3d3d3] overflow-hidden"
                >
                    {label}
                    <button
                        type="button"
                        aria-label={`Remove label ${label}`}
                        className="flex items-center justify-center w-3.5 h-3.5 shrink-0 text-[#ffffff71] hover:text-[#d3d3d3] transition-colors"
                        onClick={() => onChange(labels.filter((entry) => entry !== label))}
                    >
                        <svg viewBox="0 0 8.2251 8.2251" className="w-[8.225px] h-[8.225px]" fill="currentColor">
                            <path d="M8.09696 0.74696c0.17088-0.17088 0.17088-0.44792 0-0.6188-0.17088-0.17088-0.44792-0.17088-0.6188 0l-3.3656 3.3656-3.3656-3.3656c-0.17088-0.17088-0.44792-0.17088-0.6188 0-0.17088 0.17088-0.17088 0.44792 0 0.6188l3.3656 3.3656-3.3656 3.3656c-0.17088 0.17088-0.17088 0.44792 0 0.6188 0.17088 0.17088 0.44792 0.17088 0.6188 0l3.3656-3.3656 3.3656 3.3656c0.17088 0.17088 0.44792 0.17088 0.6188 0 0.17088-0.17088 0.17088-0.44792 0-0.6188l-3.3656-3.3656 3.3656-3.3656z" />
                        </svg>
                    </button>
                </span>
            ))}
        </div>
    );
}

function formatFullDate(dateStr: string): string {
    const d = new Date(dateStr);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });
}

function formatBytes(value: string | number): string {
    const bytes = Number(value);
    if (!Number.isFinite(bytes) || bytes <= 0) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ReadingPane({ email, account, folder, onClose }: Props) {
    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (event.key === "Escape") onClose();
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [onClose]);

    // Full message content (raw HTML body with `cid:` images inlined) is
    // fetched when a mail is opened, keyed by uid so reopening is instant.
    // `null` means the fetch failed and the list preview body is used.
    const uid = email.uid;
    const isNostr = email.source === "nostr";
    const [content, setContent] = useState<Record<string, Email | null>>({});
    const inflight = useRef<Set<string>>(new Set());

    useEffect(() => {
        if (isNostr || !account || Object.hasOwn(content, uid)) return;
        // The inflight ref dedupes StrictMode's double effect invocation;
        // there must be NO cancellation on cleanup, or run 1 gets cancelled
        // while run 2 skips the fetch and content is never set (stuck spinner).
        if (inflight.current.has(uid)) return;
        inflight.current.add(uid);
        MailboxController.getEmailContent(account, folder, uid)
            .then((response) => {
                setContent((prev) => ({
                    ...prev,
                    [uid]: response.success && response.data ? response.data : null,
                }));
            })
            .catch(() => {
                setContent((prev) => ({ ...prev, [uid]: null }));
            })
            .finally(() => {
                inflight.current.delete(uid);
            });
    }, [account, folder, uid, isNostr, content]);

    const fullEmail = Object.hasOwn(content, uid) ? content[uid] : undefined;
    const bodyEmail = fullEmail ?? email;
    const body = bodyEmail.body ?? "";
    const attachments = bodyEmail.attachments ?? [];
    const srcDoc = useMemo(() => buildEmailSrcDoc(body), [body]);

    // Session-local labels, kept per uid so reopening keeps them.
    const [labelMap, setLabelMap] = useState<Record<string, string[]>>({});
    const labels = labelMap[uid] ?? [];
    const setLabels = (next: string[]) =>
        setLabelMap((prev) => ({ ...prev, [uid]: next }));

    // The iframe reports its content height (see HEIGHT_SCRIPT) so it grows
    // with the message instead of forcing an inner scrollbar.
    const [frameHeight, setFrameHeight] = useState(400);
    useEffect(() => {
        const onMessage = (event: MessageEvent) => {
            const data = event.data as { type?: string; h?: number } | null;
            if (data?.type === "narada:email-height" && typeof data.h === "number") {
                setFrameHeight(Math.min(Math.max(data.h, 160), 8000));
            }
        };
        window.addEventListener("message", onMessage);
        return () => window.removeEventListener("message", onMessage);
    }, []);

    const downloadAttachment = async (attachment: Attachment) => {
        if (!account) {
            showToast({ content: "Attachment download is unavailable." });
            return;
        }
        try {
            const response = await MailboxController.downloadAttachment(
                account,
                folder,
                email.uid,
                attachment.name,
                attachment.cid,
            );
            const data = response.data?.data;
            if (!response.success || !data) {
                showToast({ content: "Could not download attachment." });
                return;
            }
            const bytes = Uint8Array.from(atob(data), (char) => char.charCodeAt(0));
            const blob = new Blob([bytes], {
                type: attachment.type || "application/octet-stream",
            });
            const url = URL.createObjectURL(blob);
            const anchor = document.createElement("a");
            anchor.href = url;
            anchor.download = attachment.name;
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();
            URL.revokeObjectURL(url);
        } catch {
            showToast({ content: "Could not download attachment." });
        }
    };

    const senderName = extractFullname(email.sender) || extractEmailAddress(email.sender) || "Unknown";
    const senderEmail = extractEmailAddress(email.sender);
    const initial = senderName[0]?.toUpperCase() || "?";

    const subject = email.subject || "";
    const reply = () =>
        openCompose({
            to: senderEmail,
            subject: /^re:/i.test(subject) ? subject : `Re: ${subject}`,
        });
    const forward = () =>
        openCompose({
            subject: /^fwd:/i.test(subject) || /^fw:/i.test(subject) ? subject : `Fwd: ${subject}`,
        });

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div className="absolute inset-0 bg-black/55" onClick={onClose} aria-hidden />

            <div className="relative w-[900px] max-w-[calc(100vw-48px)] max-h-[calc(100vh-48px)] bg-[#252525] rounded-xl overflow-hidden shadow-[0_12px_30px_rgba(0,0,0,0.4)] flex flex-col">
                {/* Toolbar */}
                <div className="flex items-center justify-between px-2 pt-1.5 pb-2 shrink-0">
                    <div className="flex items-center gap-2">
                        <ToolbarButton title="Archive" onClick={() => comingSoon("Archive")}>
                            <>
                                <rect x="3" y="3" width="18" height="5" rx="1" />
                                <path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" />
                                <path d="M10 12h4" />
                            </>
                        </ToolbarButton>
                        <ToolbarButton title="Reply" onClick={reply}>
                            <>
                                <polyline points="9 14 4 9 9 4" />
                                <path d="M20 20v-7a4 4 0 0 0-4-4H4" />
                            </>
                        </ToolbarButton>
                        <ToolbarButton title="Mark unread" onClick={() => comingSoon("Mark unread")}>
                            <>
                                <path d="M21.2 8.4c.5.38.8.97.8 1.6v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V10a2 2 0 0 1 .8-1.6l8-6a2 2 0 0 1 2.4 0l8 6Z" />
                                <path d="M22 10l-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 10" />
                            </>
                        </ToolbarButton>
                        <ToolbarButton title="Star" onClick={() => comingSoon("Star")}>
                            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26" />
                        </ToolbarButton>
                        <ToolbarButton title="Snooze" onClick={() => comingSoon("Snooze")}>
                            <>
                                <circle cx="12" cy="12" r="9" />
                                <polyline points="12 7 12 12 15.5 14" />
                            </>
                        </ToolbarButton>
                        <ToolbarButton title="Labels" onClick={() => comingSoon("Labels")}>
                            <>
                                <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
                                <line x1="7" y1="7" x2="7.01" y2="7" />
                            </>
                        </ToolbarButton>
                        <ToolbarButton title="Delete" onClick={() => comingSoon("Delete")}>
                            <>
                                <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
                                <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
                            </>
                        </ToolbarButton>
                        <ToolbarButton title="More" onClick={() => comingSoon("More actions")}>
                            <>
                                <circle cx="5" cy="12" r="1.5" fill="currentColor" stroke="none" />
                                <circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" />
                                <circle cx="19" cy="12" r="1.5" fill="currentColor" stroke="none" />
                            </>
                        </ToolbarButton>
                    </div>
                    <ToolbarButton title="Close (Esc)" onClick={onClose}>
                        <>
                            <line x1="18" y1="6" x2="6" y2="18" />
                            <line x1="6" y1="6" x2="18" y2="18" />
                        </>
                    </ToolbarButton>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto px-5 pb-4">
                    <div className="max-w-[800px] flex flex-col gap-3">
                        <h2 className="text-[22px]/[26px] font-semibold text-[#d3d3d3] py-0.5">
                            {email.subject || "(no subject)"}
                        </h2>

                        {/* Labels row (mockup F2: dimmed Add label + chips) */}
                        <div className="flex items-center gap-2 flex-wrap">
                            <LabelsRow key={uid} labels={labels} onChange={setLabels} />
                            <RouteBadge route={emailDeliveryRoute(email)} hollow />
                        </div>

                        {/* Sender row */}
                        <div className="relative flex items-center gap-3">
                            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#4a9eff] to-[#2383e2] flex items-center justify-center text-white text-xs font-semibold flex-shrink-0">
                                {initial}
                            </div>
                            <div className="min-w-0">
                                <div className="text-sm font-medium text-[#d3d3d3] truncate">{senderName}</div>
                                {senderEmail && senderEmail !== senderName && (
                                    <div className="text-sm text-[#7f7f7f] truncate">{senderEmail}</div>
                                )}
                            </div>
                            <div className="ml-auto flex items-center gap-2 pr-1">
                                <button
                                    type="button"
                                    title="Reply"
                                    className="w-6 h-6 rounded flex items-center justify-center text-[#ffffff71] hover:bg-white/10 hover:text-[#d3d3d3] transition-colors"
                                    onClick={reply}
                                >
                                    <Icon className="w-4 h-4">
                                        <>
                                            <polyline points="9 14 4 9 9 4" />
                                            <path d="M20 20v-7a4 4 0 0 0-4-4H4" />
                                        </>
                                    </Icon>
                                </button>
                                <button
                                    type="button"
                                    title="Forward"
                                    className="w-6 h-6 rounded flex items-center justify-center text-[#ffffff71] hover:bg-white/10 hover:text-[#d3d3d3] transition-colors"
                                    onClick={forward}
                                >
                                    <Icon className="w-4 h-4">
                                        <>
                                            <polyline points="15 14 20 9 15 4" />
                                            <path d="M4 20v-7a4 4 0 0 1 4-4h12" />
                                        </>
                                    </Icon>
                                </button>
                                <span className="text-xs text-[#7f7f7f] whitespace-nowrap">
                                    {formatFullDate(email.date)}
                                </span>
                            </div>
                        </div>

                        {/* Recipients */}
                        <div className="flex items-center gap-2 text-sm">
                            <span className="text-[#7f7f7f]">To</span>
                            <span className="text-[#d3d3d3] truncate">{email.receivers}</span>
                        </div>

                        {/* Body — the list preview renders INSTANTLY while the
                            full content upgrades in the background. Plain text
                            stays in the normal DOM; only HTML mail gets the
                            sandboxed iframe (images/video/audio/styling,
                            sanitized, auto-height). */}
                        <div className="py-2">
                            {looksLikeHtml(body) ? (
                                <iframe
                                    key={uid}
                                    title="Email body"
                                    srcDoc={srcDoc}
                                    sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox allow-downloads"
                                    style={{ height: `${frameHeight}px` }}
                                    className="w-full border-0 bg-transparent"
                                />
                            ) : (
                                <div className="text-sm leading-relaxed text-[#d3d3d3] whitespace-pre-wrap break-words">
                                    {body}
                                </div>
                            )}
                        </div>

                        {/* Attachments */}
                        {attachments.length > 0 && (
                            <div className="flex flex-wrap items-center gap-2 pt-1">
                                {attachments.map((attachment) => (
                                    <button
                                        key={`${attachment.name}-${attachment.cid ?? ""}`}
                                        type="button"
                                        title={`Download ${attachment.name}`}
                                        className="flex items-center gap-2 h-9 pl-2 pr-3 rounded-md border border-white/10 text-xs text-[#d3d3d3] hover:bg-white/10 transition-colors"
                                        onClick={() => void downloadAttachment(attachment)}
                                    >
                                        <Icon className="w-4 h-4 flex-shrink-0">
                                            <>
                                                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66L9.41 17.41a2 2 0 0 1-2.83-2.83l8.49-8.49" />
                                            </>
                                        </Icon>
                                        <span className="max-w-[180px] truncate">{attachment.name}</span>
                                        {formatBytes(attachment.size) && (
                                            <span className="text-[#7f7f7f] whitespace-nowrap">
                                                {formatBytes(attachment.size)}
                                            </span>
                                        )}
                                    </button>
                                ))}
                            </div>
                        )}

                        {/* Reply / Forward */}
                        <div className="flex items-center gap-1 pt-1">
                            <button
                                type="button"
                                className="h-8 flex items-center justify-center gap-1 px-3 rounded-md border border-white/10 text-sm font-medium text-[#d3d3d3] hover:bg-white/10 transition-colors"
                                onClick={reply}
                            >
                                <Icon className="w-4 h-4">
                                    <>
                                        <polyline points="9 14 4 9 9 4" />
                                        <path d="M20 20v-7a4 4 0 0 0-4-4H4" />
                                    </>
                                </Icon>
                                Reply
                            </button>
                            <button
                                type="button"
                                className="h-8 flex items-center justify-center gap-1 px-3 rounded-md border border-white/10 text-sm font-medium text-[#d3d3d3] hover:bg-white/10 transition-colors"
                                onClick={forward}
                            >
                                <Icon className="w-4 h-4">
                                    <>
                                        <polyline points="15 14 20 9 15 4" />
                                        <path d="M4 20v-7a4 4 0 0 1 4-4h12" />
                                    </>
                                </Icon>
                                Forward
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
