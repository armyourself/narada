<script lang="ts">
    import { SharedStore } from "$lib/stores/shared.svelte";
    import Compose from "$lib/ui/Layout/Main/Content/Compose.svelte";
    import { showThis as showContent } from "$lib/ui/Layout/Main/Content.svelte";
    import { extractEmailAddress, extractFullname } from "$lib/utils";
    import RouteBadge, { emailRoute } from "$lib/ui/Components/RouteBadge.svelte";
    import type { Email } from "$lib/types";

    interface Contact {
        name: string;
        addr: string;
        initial: string;
        color: string;
        route: "direct" | "relay" | "gateway";
    }

    const CONTACT_COLORS = ["#C99B76", "#A97635", "#4C7A61", "#8FA9C4", "#B98CA0", "#7C6A5E"];

    let searchQuery = $state("");

    /**
     * Contacts are derived from senders seen in any loaded mailbox —
     * people you've actually exchanged mail with, matching the mockup's
     * description. No persistent contact store exists yet.
     */
    let contacts = $derived.by(() => {
        const byAddr = new Map<string, Contact>();
        Object.values(SharedStore.mailboxes).forEach((mailbox) => {
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
    });

    let filteredContacts = $derived.by(() => {
        const q = searchQuery.trim().toLowerCase();
        if (!q) return contacts;
        return contacts.filter((c) =>
            (c.name + c.addr).toLowerCase().includes(q),
        );
    });

    function messageContact(contact: Contact) {
        showContent(Compose, {
            initialReceiver: contact.addr,
        });
    }
</script>

<div class="contacts-panel active">
    <div class="settings-title">Contacts</div>
    <div class="settings-sub">People you've exchanged keys with.</div>

    <div class="contacts-search">
        <div class="search-box">
            <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
            <input type="text" bind:value={searchQuery} placeholder="Search contacts" />
        </div>
    </div>

    <div class="settings-section" style="border-bottom:none;">
        {#if filteredContacts.length === 0}
            <div class="empty-note">
                {#if searchQuery}
                    No contacts match “{searchQuery}”.
                {:else}
                    No contacts yet — people you've exchanged mail with will appear here.
                {/if}
            </div>
        {:else}
            <div class="contact-list">
                {#each filteredContacts as contact (contact.addr)}
                    <div class="contact-row">
                        <div class="avatar" style="background:{contact.color};">{contact.initial}</div>
                        <div class="contact-main">
                            <div class="contact-name">{contact.name}</div>
                            <div class="contact-addr">{contact.addr}</div>
                        </div>
                        <RouteBadge route={contact.route} />
                        <button
                            class="icon-mini-btn"
                            onclick={() => messageContact(contact)}
                            title="Message"
                            aria-label="Message {contact.name}"
                        >
                            <svg viewBox="0 0 24 24"><path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7Z"/></svg>
                        </button>
                    </div>
                {/each}
            </div>
        {/if}
    </div>
</div>

<style>
    :global {
        .contacts-panel {
            flex-grow: 1;
            display: none;
            flex-direction: column;
            background: var(--cream);
            padding: 32px 44px;
            overflow-y: auto;
            min-width: 0;
        }

        .contacts-panel.active {
            display: flex;
        }

        .contacts-panel .settings-title {
            font-family: var(--ui);
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 6px;
        }

        .contacts-panel .settings-sub {
            font-size: 0.82rem;
            color: var(--ink-faint);
            margin-bottom: 34px;
        }

        .contacts-panel .contacts-search {
            margin-bottom: 22px;
            max-width: 340px;
        }

        .contacts-panel .search-box {
            background: var(--glass-strong);
            border: 1px solid var(--glass-border);
            border-radius: 100px;
            padding: 9px 15px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .contacts-panel .search-box svg {
            width: 15px;
            height: 15px;
            stroke: var(--ink-faint);
            fill: none;
            stroke-width: 2;
            flex-shrink: 0;
        }

        .contacts-panel .search-box input {
            border: none;
            background: transparent;
            outline: none;
            width: 100%;
            font-size: 0.85rem;
            color: var(--ink);
            font-family: var(--body);
        }

        .contacts-panel .search-box input::placeholder {
            color: var(--ink-faint);
        }

        .contacts-panel .settings-section {
            max-width: 560px;
        }

        .contacts-panel .contact-row {
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 12px 0;
            border-bottom: 1px solid var(--glass-border);
        }

        .contacts-panel .contact-row:last-child {
            border-bottom: none;
        }

        .contacts-panel .avatar {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            font-size: 0.72rem;
            font-family: var(--ui);
            font-weight: 600;
            flex-shrink: 0;
        }

        .contacts-panel .contact-main {
            flex: 1;
            min-width: 0;
        }

        .contacts-panel .contact-name {
            font-size: 0.86rem;
            font-weight: 600;
            color: var(--ink);
        }

        .contacts-panel .contact-addr {
            font-size: 0.72rem;
            color: var(--ink-faint);
            font-family: var(--ui);
            word-break: break-all;
        }

        .contacts-panel .icon-mini-btn {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--ink-faint);
            flex-shrink: 0;
        }

        .contacts-panel .icon-mini-btn:hover {
            background: var(--glass-strong);
            color: var(--accent);
        }

        .contacts-panel .icon-mini-btn svg {
            width: 14px;
            height: 14px;
            stroke: currentColor;
            fill: none;
            stroke-width: 2;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        .contacts-panel .empty-note {
            padding: 24px 0;
            color: var(--ink-faint);
            font-size: 0.82rem;
        }
    }
</style>
