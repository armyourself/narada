<script lang="ts">
    import {
        MainNav,
        showView,
        toggleRouteFilter,
        type DeliveryRoute,
    } from "$lib/stores/mainNav.svelte";
    import { SharedStore } from "$lib/stores/shared.svelte";
    import Mailbox, { getCurrentMailbox } from "$lib/ui/Layout/Main/Content/Mailbox.svelte";
    import { MailboxController } from "$lib/mailbox";
    import Compose from "$lib/ui/Layout/Main/Content/Compose.svelte";
    import { showThis as showContent } from "$lib/ui/Layout/Main/Content.svelte";
    import { show as showMessage } from "$lib/ui/Components/Message";
    import { local } from "$lib/locales";
    import { DEFAULT_LANGUAGE } from "$lib/constants";
    import { nostrIdentity } from "$lib/nostr/identity.svelte";
    import type { Account } from "$lib/types";

    interface FolderItem {
        id: string;
        label: string;
        icon: string;
        folder?: string;
    }

    const folders: FolderItem[] = [
        { id: "inbox", label: "Inbox", icon: '<path d="M3 12h4l2 4h6l2-4h4"/><path d="M5 5h14l2 7v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-6l2-7Z"/>', folder: "Inbox" },
        { id: "starred", label: "Starred", icon: '<path d="M12 3l2.6 5.9 6.4.6-4.8 4.3 1.4 6.3L12 17l-5.6 3.1 1.4-6.3-4.8-4.3 6.4-.6L12 3Z"/>', folder: "Flagged" },
        { id: "sent", label: "Sent", icon: '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7Z"/>', folder: "Sent" },
        { id: "drafts", label: "Drafts", icon: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>', folder: "Drafts" },
        { id: "all", label: "All mail", icon: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 8h18"/>', folder: "All" },
        { id: "encrypted", label: "Encrypted", icon: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>', folder: "Encrypted" },
        { id: "network", label: "Node network", icon: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8.5 6h7"/><path d="M8 7.5 10.5 15.5"/><path d="M16 7.5 13.5 15.5"/>' },
        { id: "trash", label: "Trash", icon: '<path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>', folder: "Trash" },
    ];

    const routes: { id: DeliveryRoute; label: string }[] = [
        { id: "direct", label: "Direct" },
        { id: "relay", label: "Via relay" },
        { id: "gateway", label: "Via gateway" },
    ];

    let isCollapsed = $state(false);
    let isLoadingFolder = $state(false);
    let relayCount = $state(0);
    let relaysConnected = $state(false);

    let currentAccount = $derived(
        SharedStore.currentAccount !== "home"
            ? (SharedStore.currentAccount as Account)
            : SharedStore.accounts[0],
    );

    let unreadCount = $derived.by(() => {
        const mailbox = SharedStore.mailboxes[currentAccount?.email_address ?? ""];
        if (!mailbox) return 0;
        return mailbox.emails.current.filter(
            (email) => !(email.flags ?? []).includes("\\Seen"),
        ).length;
    });

    let draftCount = $derived.by(() => {
        const mailbox = SharedStore.mailboxes[currentAccount?.email_address ?? ""];
        if (!mailbox) return 0;
        return mailbox.folder === "Drafts"
            ? mailbox.total
            : mailbox.emails.current.filter((email) =>
                  (email.flags ?? []).includes("\\Draft"),
              ).length;
    });

    let nostrId = $derived(
        nostrIdentity.state.npub
            ? nostrIdentity.state.npub.slice(0, 12) +
              "…" +
              nostrIdentity.state.npub.slice(-4)
            : nostrIdentity.state.publicId
                ? nostrIdentity.state.publicId.slice(0, 12) +
                  "…" +
                  nostrIdentity.state.publicId.slice(-4)
                : "not set",
    );

    let peerPillText = $derived.by(() => {
        if (relayCount > 0) return `${relayCount} relay${relayCount !== 1 ? "s" : ""} connected`;
        return "node offline";
    });

    async function fetchRelayStatus() {
        try {
            const res = await fetch(`${SharedStore.server}/nostr/relays`);
            const json = await res.json();
            if (json.success && Array.isArray(json.data)) {
                relayCount = json.data.filter((r: any) => r.connected).length;
                relaysConnected = relayCount > 0;
            }
        } catch {
            relayCount = 0;
            relaysConnected = false;
        }
    }

    // Poll relay status every 30s
    let relayPollInterval: ReturnType<typeof setInterval> | null = null;
    import { onMount, onDestroy } from "svelte";

    onMount(() => {
        fetchRelayStatus();
        relayPollInterval = setInterval(fetchRelayStatus, 30000);
    });

    onDestroy(() => {
        if (relayPollInterval) clearInterval(relayPollInterval);
    });

    async function selectFolder(item: FolderItem) {
        if (item.id === "network") {
            showView("network");
            return;
        }
        showView("inbox");
        MainNav.folder = item.id;
        if (!item.folder || !currentAccount) return;

        isLoadingFolder = true;
        try {
            if (getCurrentMailbox()?.folder !== item.folder) {
                const response = await MailboxController.getMailbox(
                    currentAccount,
                    item.folder,
                );
                if (!response.success) {
                    showMessage({
                        title: local.error_get_mailbox[DEFAULT_LANGUAGE],
                    });
                    console.error(response.message);
                    return;
                }
            }
        } finally {
            isLoadingFolder = false;
        }
    }

    function openCompose() {
        showContent(Compose);
    }
</script>

<div class="menu-panel" class:collapsed={isCollapsed}>
    <button class="collapse-btn" onclick={() => (isCollapsed = !isCollapsed)} title={isCollapsed ? "Show menu" : "Hide menu"} aria-label={isCollapsed ? "Show menu" : "Hide menu"}>
        <svg viewBox="0 0 24 24"><path d="m15 18-6-6 6-6"/></svg>
    </button>
    <div class="menu-inner">
        <div class="menu-header">
            <h2>Narada</h2>
        </div>
        <div class="peer-pill" class:online={relaysConnected}>
            <span class="live"></span> {peerPillText}
        </div>

        <button class="btn-new" onclick={openCompose}>
            <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
            Compose
        </button>

        <ul class="folder-list">
            {#each folders as folder}
                <li class:active={MainNav.view === "inbox" && MainNav.folder === folder.id}>
                    <button onclick={() => selectFolder(folder)} title={folder.label}>
                        <svg viewBox="0 0 24 24">{@html folder.icon}</svg>
                        <span class="label-text">{folder.label}</span>
                        {#if folder.id === "inbox" && unreadCount > 0}
                            <span class="fbadge">{unreadCount}</span>
                        {:else if folder.id === "drafts" && draftCount > 0}
                            <span class="fbadge">{draftCount}</span>
                        {/if}
                    </button>
                </li>
            {/each}
        </ul>

        <div class="routes-header"><span>Delivery route</span></div>
        <ul class="route-list">
            {#each routes as route}
                <li class:active={MainNav.routeFilter === route.id}>
                    <button onclick={() => toggleRouteFilter(route.id)} title={route.label}>
                        <span class="rdot {route.id}"></span>
                        {route.label}
                    </button>
                </li>
            {/each}
        </ul>

        <div class="menu-foot">
            <div class="node-id">
                <span class="id-label">your node</span>
                <span class="id-val">{nostrId}</span>
            </div>
        </div>
    </div>
</div>

<style>
    :global {
        .menu-panel {
            width: 250px;
            border-right: 1px solid var(--glass-border);
            display: flex;
            flex-direction: column;
            background: var(--glass-strong);
            flex-shrink: 0;
            overflow: hidden;
            transition: width 0.25s ease;
            position: relative;
        }

        .menu-panel.collapsed {
            width: 0;
            border-right: none;
        }

        .menu-panel.collapsed .menu-inner {
            opacity: 0;
            pointer-events: none;
        }

        /* Collapse toggle stays visible when the panel is collapsed; it
           floats over the email list at the panel's former right edge. */
        .menu-panel .collapse-btn {
            position: absolute;
            top: 26px;
            right: 10px;
            z-index: 3;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--ink-faint);
            background: var(--glass-solid);
            border: 1px solid var(--glass-border);
        }

        .menu-panel .collapse-btn:hover {
            color: var(--ink);
        }

        .menu-panel .collapse-btn svg {
            width: 14px;
            height: 14px;
            stroke: currentColor;
            fill: none;
            stroke-width: 2.2;
            stroke-linecap: round;
            stroke-linejoin: round;
            transition: transform 0.25s ease;
        }

        .menu-panel.collapsed .collapse-btn {
            right: -44px;
        }

        .menu-panel.collapsed .collapse-btn svg {
            transform: rotate(180deg);
        }

        .menu-inner {
            display: flex;
            flex-direction: column;
            height: 100%;
            min-width: 250px;
            transition: opacity 0.15s ease;
            padding: 26px 18px;
        }

        .menu-inner .menu-header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 24px;
        }

        .menu-inner .menu-header h2 {
            font-family: var(--ui);
            font-size: 1.05rem;
            font-weight: 600;
        }

        .menu-inner .peer-pill {
            display: flex;
            align-items: center;
            gap: 6px;
            font-family: var(--ui);
            font-size: 0.62rem;
            color: var(--ink-dim);
            background: var(--glass-solid);
            border: 1px solid var(--glass-border);
            padding: 4px 10px;
            border-radius: 100px;
            margin-bottom: 20px;
            width: fit-content;
        }

        .menu-inner .peer-pill .live {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--ink-faint);
        }

        .menu-inner .peer-pill.online .live {
            background: var(--direct);
        }

        .menu-inner .btn-new {
            background: var(--glass-solid);
            border: 1px solid var(--glass-border);
            color: var(--ink);
            padding: 12px;
            border-radius: var(--radius-sm);
            font-weight: 600;
            font-family: var(--ui);
            font-size: 0.85rem;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 10px;
            margin-bottom: 26px;
            box-shadow: 0 4px 14px rgba(203, 154, 115, 0.20);
            transition: transform 0.18s ease, box-shadow 0.18s ease;
        }

        .menu-inner .btn-new svg {
            width: 15px;
            height: 15px;
            stroke: var(--accent);
            fill: none;
            stroke-width: 2.4;
            stroke-linecap: round;
        }

        .menu-inner .btn-new:hover {
            transform: translateY(-1px);
            box-shadow: 0 8px 20px rgba(203, 154, 115, 0.28);
        }

        .menu-inner .folder-list {
            list-style: none;
            margin-bottom: 28px;
        }

        .menu-inner .folder-list li {
            margin-bottom: 3px;
            border-radius: var(--radius-sm);
            border-left: 2px solid transparent;
            transition: background 0.15s, color 0.15s, border-color 0.15s;
        }

        .menu-inner .folder-list li:hover,
        .menu-inner .folder-list li.active {
            background: var(--glass-solid);
        }

        .menu-inner .folder-list li.active {
            border-left-color: var(--accent);
        }

        .menu-inner .folder-list li button {
            padding: 9px 11px;
            display: flex;
            align-items: center;
            gap: 13px;
            width: 100%;
            color: var(--ink-dim);
            font-size: 0.85rem;
            font-weight: 500;
            border-radius: var(--radius-sm);
            text-align: left;
        }

        .menu-inner .folder-list li.active button {
            color: var(--ink);
        }

        .menu-inner .folder-list li svg {
            width: 16px;
            height: 16px;
            stroke: var(--ink-faint);
            fill: none;
            stroke-width: 2;
            stroke-linecap: round;
            stroke-linejoin: round;
            flex-shrink: 0;
        }

        .menu-inner .folder-list li.active svg {
            stroke: var(--accent);
        }

        .menu-inner .folder-list .label-text {
            flex: 1;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .menu-inner .fbadge {
            background: var(--accent);
            color: #fff;
            font-size: 0.6rem;
            padding: 1px 7px;
            border-radius: 100px;
            margin-left: auto;
            font-family: var(--ui);
        }

        .menu-inner .routes-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.66rem;
            color: var(--ink-faint);
            text-transform: uppercase;
            font-weight: 600;
            letter-spacing: 0.03em;
            margin-bottom: 12px;
            padding: 0 11px;
        }
        .menu-inner .route-list {
            list-style: none;
            margin-bottom: 20px;
        }

        .menu-inner .route-list li {
            border-radius: var(--radius-sm);
            transition: background 0.15s, color 0.15s;
        }

        .menu-inner .route-list li:hover,
        .menu-inner .route-list li.active {
            background: var(--glass-solid);
        }

        .menu-inner .route-list li button {
            padding: 7px 11px;
            display: flex;
            align-items: center;
            gap: 11px;
            width: 100%;
            color: var(--ink-dim);
            font-size: 0.8rem;
            border-radius: var(--radius-sm);
            text-align: left;
        }

        .menu-inner .route-list li.active button {
            color: var(--ink);
            font-weight: 600;
        }


        .menu-inner .rdot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            flex-shrink: 0;
        }

        .menu-inner .rdot.direct { background: var(--direct); }
        .menu-inner .rdot.relay { background: var(--relay); }
        .menu-inner .rdot.gateway { background: var(--gateway); }

        .menu-inner .menu-foot {
            margin-top: auto;
            padding-top: 16px;
            border-top: 1px solid var(--glass-border);
        }

        .menu-inner .node-id {
            font-family: var(--ui);
            font-size: 0.64rem;
            color: var(--ink-faint);
            display: flex;
            flex-direction: column;
            gap: 5px;
        }

        .menu-inner .node-id .id-val {
            color: var(--ink-dim);
            word-break: break-all;
        }
    }
</style>
