import { useMainNav } from "@/lib/stores/mainNav";
import { useSharedStore } from "@/lib/stores/shared";
import type { Email } from "@/lib/types";

// Single place that flips a message to \Seen in the cached mailbox, so list
// rows and the search palette both get read-state updates.
export function markEmailAsRead(email: Email) {
    const state = useSharedStore.getState();
    const accountAddress =
        state.currentAccount !== "home"
            ? state.currentAccount.email_address
            : state.accounts[0]?.email_address;
    if (!accountAddress) return;
    const mailbox = state.mailboxes[accountAddress];
    if (!mailbox) return;
    if ((email.flags ?? []).includes("\\Seen")) return;
    useSharedStore.setState({
        mailboxes: {
            ...state.mailboxes,
            [accountAddress]: {
                ...mailbox,
                emails: {
                    ...mailbox.emails,
                    current: mailbox.emails.current.map((entry) =>
                        entry.message_id === email.message_id &&
                        !(entry.flags ?? []).includes("\\Seen")
                            ? { ...entry, flags: [...(entry.flags ?? []), "\\Seen"] }
                            : entry,
                    ),
                },
            },
        },
    });
}

// Open a message in the reading pane (and mark it read).
export function openEmailInPane(email: Email) {
    useMainNav.getState().selectEmail(email);
    markEmailAsRead(email);
}
