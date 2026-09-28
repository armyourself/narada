"use client";

import { useMemo, useState } from "react";
import { useSharedStore } from "@/lib/stores/shared";
import type { DeliveryRoute } from "@/lib/stores/mainNav";
import { openCompose } from "@/lib/stores/ui";
import { extractEmailAddress, extractFullname } from "@/lib/utils";
import type { Email } from "@/lib/types";
import RouteBadge, { emailRoute } from "./RouteBadge";
import "./contacts.css";

interface Contact {
    name: string;
    addr: string;
    initial: string;
    color: string;
    route: DeliveryRoute;
}

const CONTACT_COLORS = ["#C99B76", "#A97635", "#4C7A61", "#8FA9C4", "#B98CA0", "#7C6A5E"];

export default function Contacts() {
    const mailboxes = useSharedStore((s) => s.mailboxes);
    const [searchQuery, setSearchQuery] = useState("");

    /**
     * Contacts are derived from senders seen in any loaded mailbox —
     * people you've actually exchanged mail with, matching the mockup's
     * description. No persistent contact store exists yet.
     */
    const contacts = useMemo(
        () => {
            const byAddr = new Map<string, Contact>();
            Object.values(mailboxes).forEach((mailbox) => {
                mailbox.emails.current.forEach((email: Email) => {
                    const addr = extractEmailAddress(email.sender);
                    if (!addr || byAddr.has(addr)) return;
                    const name =
                        extractFullname(email.sender) || addr.split("@")[0];
                    byAddr.set(addr, {
                        name,
                        addr,
                        initial: (name[0] ?? "?").toUpperCase(),
                        color: CONTACT_COLORS[byAddr.size % CONTACT_COLORS.length],
                        route: emailRoute(email),
                    });
                });
            });
            return Array.from(byAddr.values());
        },
        [mailboxes],
    );

    const filteredContacts = useMemo(
        () => {
            const q = searchQuery.trim().toLowerCase();
            if (!q) return contacts;
            return contacts.filter((c) =>
                (c.name + c.addr).toLowerCase().includes(q),
            );
        },
        [contacts, searchQuery],
    );

    const messageContact = (contact: Contact) => {
        openCompose({ to: contact.addr });
    };

    return (
        <div className="contacts-panel active">
            <div className="settings-title">Contacts</div>
            <div className="settings-sub">{"People you've exchanged keys with."}</div>

            <div className="contacts-search">
                <div className="search-box">
                    <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>
                    <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search contacts"
                    />
                </div>
            </div>

            <div className="settings-section" style={{ borderBottom: "none" }}>
                {filteredContacts.length === 0 ? (
                    <div className="empty-note">
                        {searchQuery ? (
                            <>No contacts match “{searchQuery}”.</>
                        ) : (
                            <>{"No contacts yet — people you've exchanged mail with will appear here."}</>
                        )}
                    </div>
                ) : (
                    <div className="contact-list">
                        {filteredContacts.map((contact) => (
                            <div className="contact-row" key={contact.addr}>
                                <div className="avatar" style={{ background: contact.color }}>{contact.initial}</div>
                                <div className="contact-main">
                                    <div className="contact-name">{contact.name}</div>
                                    <div className="contact-addr">{contact.addr}</div>
                                </div>
                                <RouteBadge route={contact.route} />
                                <button
                                    className="icon-mini-btn"
                                    onClick={() => messageContact(contact)}
                                    title="Message"
                                    aria-label={`Message ${contact.name}`}
                                >
                                    <svg viewBox="0 0 24 24"><path d="M22 2 11 13" /><path d="M22 2 15 22l-4-9-9-4 20-7Z" /></svg>
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
