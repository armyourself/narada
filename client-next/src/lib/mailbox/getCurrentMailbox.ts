import { Folder, type Mailbox } from "@/lib/types";
import type { SharedState, SharedStoreKeys } from "@/lib/stores/shared";

export function getCurrentMailbox(
    state: {
        currentAccount: SharedState[SharedStoreKeys.currentAccount];
        mailboxes: SharedState[SharedStoreKeys.mailboxes];
    },
): Mailbox | undefined {
    if (state.currentAccount === "home") {
        const merged: Mailbox = {
            total: 0,
            emails: { prev: [], current: [], next: [] },
            folder: Folder.Inbox,
        };
        Object.values(state.mailboxes).forEach((mailbox) => {
            if (!mailbox) return;
            merged.total += mailbox.total;
            merged.emails.prev.push(...mailbox.emails.prev);
            merged.emails.current.push(...mailbox.emails.current);
            merged.emails.next.push(...mailbox.emails.next);
        });
        Object.values(merged.emails).forEach((emails) => {
            emails.sort(
                (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime(),
            );
        });
        return merged;
    }

    return state.mailboxes[state.currentAccount.email_address];
}
