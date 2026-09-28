"use client";

import { useState } from "react";
import type { SearchCriteria } from "@/lib/types";

interface Props {
    initial: SearchCriteria;
    onApply: (criteria: SearchCriteria) => void;
    onClear: () => void;
    onClose: () => void;
    busy?: boolean;
}

const splitList = (value: string): string[] =>
    value
        .split(",")
        .map((entry) => entry.trim())
        .filter(Boolean);

const inputClass =
    "w-full bg-notion-surface border border-notion-border rounded-md px-2 py-1.5 text-xs text-notion-text placeholder:text-notion-text-muted focus:border-notion-accent focus:outline-none transition-colors [color-scheme:dark]";

function Field({
    label,
    value,
    placeholder,
    onChange,
    type = "text",
}: {
    label: string;
    value: string;
    placeholder?: string;
    onChange: (value: string) => void;
    type?: string;
}) {
    return (
        <label className="flex flex-col gap-1 min-w-0">
            <span className="text-[11px] font-medium text-notion-text-secondary">
                {label}
            </span>
            <input
                type={type}
                className={inputClass}
                value={value}
                placeholder={placeholder}
                onChange={(event) => onChange(event.target.value)}
            />
        </label>
    );
}

function Toggle({
    label,
    checked,
    onChange,
}: {
    label: string;
    checked: boolean;
    onChange: (checked: boolean) => void;
}) {
    return (
        <label className="flex items-center gap-1.5 text-xs text-notion-text-secondary cursor-pointer select-none">
            <input
                type="checkbox"
                className="accent-notion-accent"
                checked={checked}
                onChange={(event) => onChange(event.target.checked)}
            />
            {label}
        </label>
    );
}

export default function SearchPanel({
    initial,
    onApply,
    onClear,
    onClose,
    busy = false,
}: Props) {
    const [from, setFrom] = useState((initial.senders ?? []).join(", "));
    const [to, setTo] = useState((initial.receivers ?? []).join(", "));
    const [cc, setCc] = useState((initial.cc ?? []).join(", "));
    const [subject, setSubject] = useState(initial.subject ?? "");
    const [include, setInclude] = useState(initial.include ?? "");
    const [exclude, setExclude] = useState(initial.exclude ?? "");
    const [since, setSince] = useState(initial.since ?? "");
    const [before, setBefore] = useState(initial.before ?? "");
    const [hasAttachments, setHasAttachments] = useState(
        initial.has_attachments === true,
    );
    const [unreadOnly, setUnreadOnly] = useState(
        (initial.excluded_flags ?? []).some(
            (flag) => flag.toLowerCase() === "\\seen",
        ),
    );
    const [starredOnly, setStarredOnly] = useState(
        (initial.included_flags ?? []).some(
            (flag) => flag.toLowerCase() === "\\flagged",
        ),
    );

    const build = (): SearchCriteria => {
        const criteria: SearchCriteria = {};
        const senders = splitList(from);
        const receivers = splitList(to);
        const ccList = splitList(cc);
        if (senders.length) criteria.senders = senders;
        if (receivers.length) criteria.receivers = receivers;
        if (ccList.length) criteria.cc = ccList;
        if (subject.trim()) criteria.subject = subject.trim();
        if (include.trim()) criteria.include = include.trim();
        if (exclude.trim()) criteria.exclude = exclude.trim();
        if (since) criteria.since = since;
        if (before) criteria.before = before;
        if (hasAttachments) criteria.has_attachments = true;
        if (unreadOnly) criteria.excluded_flags = ["\\Seen"];
        if (starredOnly) criteria.included_flags = ["\\Flagged"];
        return criteria;
    };

    return (
        <section className="border-b border-notion-border px-6 py-3 bg-notion-canvas space-y-3">
            <div className="flex items-center justify-between">
                <h2 className="text-xs font-semibold text-notion-text">
                    Advanced search
                </h2>
                <button
                    type="button"
                    className="p-1 text-notion-text-muted hover:text-notion-text hover:bg-notion-hover rounded transition-colors"
                    title="Close"
                    onClick={onClose}
                >
                    <svg
                        className="w-3.5 h-3.5"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                    >
                        <path d="M18 6 6 18M6 6l12 12" />
                    </svg>
                </button>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Field
                    label="From"
                    value={from}
                    placeholder="alice@example.com, bob@…"
                    onChange={setFrom}
                />
                <Field
                    label="To"
                    value={to}
                    placeholder="carol@example.com"
                    onChange={setTo}
                />
                <Field label="CC" value={cc} placeholder="list@…" onChange={setCc} />
                <Field
                    label="Subject"
                    value={subject}
                    placeholder="quarterly report"
                    onChange={setSubject}
                />
                <Field
                    label="Has the words"
                    value={include}
                    placeholder="invoice, meeting"
                    onChange={setInclude}
                />
                <Field
                    label="Doesn't have"
                    value={exclude}
                    placeholder="newsletter"
                    onChange={setExclude}
                />
                <Field
                    label="Since"
                    type="date"
                    value={since}
                    onChange={setSince}
                />
                <Field
                    label="Before"
                    type="date"
                    value={before}
                    onChange={setBefore}
                />
            </div>

            <div className="flex items-center justify-between gap-4 flex-wrap">
                <div className="flex items-center gap-4">
                    <Toggle
                        label="Has attachment"
                        checked={hasAttachments}
                        onChange={setHasAttachments}
                    />
                    <Toggle
                        label="Unread"
                        checked={unreadOnly}
                        onChange={setUnreadOnly}
                    />
                    <Toggle
                        label="Starred"
                        checked={starredOnly}
                        onChange={setStarredOnly}
                    />
                </div>
                <div className="flex items-center gap-2">
                    <button
                        type="button"
                        className="px-3 py-1 rounded-md border border-notion-border text-xs font-medium text-notion-text-secondary hover:bg-notion-hover transition-colors"
                        onClick={onClear}
                        disabled={busy}
                    >
                        Clear
                    </button>
                    <button
                        type="button"
                        className="px-3 py-1 rounded-md bg-notion-accent text-white text-xs font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
                        onClick={() => onApply(build())}
                        disabled={busy}
                    >
                        {busy ? "Searching…" : "Search"}
                    </button>
                </div>
            </div>
        </section>
    );
}
