export type OpenmailTaskResults<T> = {
    [email_address: string]: T;
};

export interface LocalAvatar {
    bg: string;
    fg: string;
    initials: string;
}

export interface Gravatar {
    hash: string;
    fullname?: string;
}

export interface INotificationHandler {
    account: Account;
    initialize(): void;
    terminate(): void;
    reinitialize(): void;
    areNotificationsAllowed(): boolean;
    pushDesktopNotification(title?: string, body?: string): void;
}

export interface Account {
    avatar: Gravatar | LocalAvatar;
    email_address: string;
    fullname?: string;
}

export interface Email {
    message_id: string;
    uid: string;
    // Either Name Surname <namesurname@domain.com> or namesurname@domain.com
    sender: string;
    // mail addresses separated by comma
    receivers: string;
    date: string;
    subject: string;
    body: string;
    // mail addresses separated by comma
    cc?: string;
    // mail addresses separated by comma
    bcc?: string;
    flags?: string[];
    attachments?: Attachment[];
    in_reply_to?: string;
    references?: string;
    list_unsubscribe?: string;
    list_unsubscribe_post?: string;
    // Transport the message arrived on: "imap" (SMTP gateway) or "nostr"
    source?: string;
    // Delivery route reported by the backend:
    // "direct" (native Nostr), "relay" (Nostr carrying a conventional
    // address), "gateway" (conventional IMAP/SMTP email)
    route?: "direct" | "relay" | "gateway";
}

export interface SearchCriteria {
    message_id?: string[];
    senders?: string[];
    receivers?: string[];
    cc?: string[];
    subject?: string;
    since?: string;
    before?: string;
    smaller_than?: number;
    larger_than?: number;
    include?: string;
    exclude?: string;
    included_flags?: string[];
    excluded_flags?: string[];
    has_attachments?: boolean;
}

export interface Attachment {
    name: string;
    size: string;
    type: string;
    data: string;
    path?: string;
    cid?: string;
}

export interface Draft {
    // Either Name Surname <namesurname@domain.com> or namesurname@domain.com
    sender: string;
    receivers: string | string[];
    //date: string;
    subject: string;
    body: string;
    cc?: string | string[];
    bcc?: string | string[];
    attachments?: Attachment[];
    in_reply_to?: string;
    references?: string;
    metadata?: Record<string, string>;
    mail_options?: string[];
    rcpt_options?: string[];
}

export interface RawMailbox {
    folder: string;
    emails: Email[];
    total: number;
}

export interface Mailbox {
    folder: string;
    emails: { prev: Email[]; current: Email[]; next: Email[] };
    total: number;
}

export interface Flags {
    uid: string;
    flags: string[];
}

export enum Mark {
    Flagged = "\\Flagged",
    Seen = "\\Seen",
    Answered = "\\Answered",
    Draft = "\\Draft",
    Deleted = "\\Deleted",
    Unflagged = "\\Unflagged",
    Unseen = "\\Unseen",
    Unanswered = "\\Unanswered",
    Undraft = "\\Undraft",
    Undeleted = "\\Undeleted",
}

export enum Folder {
    Inbox = "Inbox",
    Flagged = "Flagged",
    Important = "Important",
    Sent = "Sent",
    Drafts = "Drafts",
    All = "All",
    Archive = "Archive",
    Junk = "Junk",
    Trash = "Trash",
}

export enum Size {
    Bytes = "Bytes",
    KB = "KB",
    MB = "MB",
}

export interface OriginalMessageContext {
    composeType: "reply" | "forward";
    messageId: string;
    sender: string;
    receivers: string;
    subject: string;
    body: string;
    date: string;
}

// A hit from POST /search-all: an Email tagged with the account it came from.
export interface SearchResult extends Email {
    account: string;
}

export interface SearchAllData {
    results: SearchResult[];
    total: number;
    accounts: string[];
}

// Contact entry from GET /nostr/directory (recipient autocomplete source).
export interface DirectoryContact {
    id: string;
    npub: string | null;
    address: string | null;
    name: string;
    self: boolean;
    account: string | null;
    messages: number;
    last_seen: string;
}

export interface DirectoryData {
    contacts: DirectoryContact[];
    total: number;
}
