import type { Email } from "@/lib/types";

// Shared row-display helpers for mailbox list rows and the search palette.

export function formatListTime(dateStr: string): string {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
        return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    } else if (diffDays === 1) {
        return "Yesterday";
    } else if (diffDays < 7) {
        return d.toLocaleDateString([], { weekday: "short" });
    } else {
        return d.toLocaleDateString([], { month: "short", day: "numeric" });
    }
}

export function getSenderName(email: Email): string {
    const from = (email as { from?: string }).from || email.sender || "";
    const match = from.match(/"?([^"<]+)"?\s*</);
    return match ? match[1].trim() : from.split("@")[0] || "Unknown";
}

export function getSubject(email: Email): string {
    return email.subject || "(no subject)";
}

export function getSnippet(email: Email): string {
    return (email.body ?? "")
        .replace(/<style[\s\S]*?<\/style>/gi, " ")
        .replace(/<[^>]+>/g, " ")
        .replace(/&nbsp;/g, " ")
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 160);
}

export function isUnread(email: Email): boolean {
    return !(email.flags ?? []).includes("\\Seen");
}
