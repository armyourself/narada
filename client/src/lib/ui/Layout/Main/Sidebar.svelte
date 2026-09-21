<script lang="ts">
    import { onMount } from "svelte";
    import { MainNav, showView, type MainView } from "$lib/stores/mainNav.svelte";
    import { SharedStore } from "$lib/stores/shared.svelte";
    import { PreferenceManager, Theme } from "$lib/preferences";
    import { MailboxController } from "$lib/mailbox";
    import { nostrIdentity } from "$lib/nostr/identity.svelte";
    import { show as showMessage } from "$lib/ui/Components/Message";
    import { local } from "$lib/locales";
    import { DEFAULT_LANGUAGE } from "$lib/constants";
    import type { Account } from "$lib/types";

    interface NavItem {
        id: string;
        view: string;
        label: string;
        icon: string;
        badge?: number;
        folder?: string;
    }

    const views: NavItem[] = [
        { id: "inbox", view: "inbox", label: "Inbox", icon: "inbox", folder: "Inbox" },
        { id: "sent", view: "sent", label: "Sent", icon: "send", folder: "Sent" },
        { id: "drafts", view: "drafts", label: "Drafts", icon: "file-edit", folder: "Drafts" },
    ];

    const mailFolders: NavItem[] = [
        { id: "all-mail", view: "all-mail", label: "All Mail", icon: "archive", folder: "All" },
        { id: "starred", view: "starred", label: "Starred", icon: "star", folder: "Flagged" },
        { id: "encrypted", view: "encrypted", label: "Encrypted", icon: "lock", folder: "Encrypted" },
    ];

    let isDark = $state(
        typeof document !== "undefined" &&
            document.documentElement.classList.contains("dark"),
    );
    let relayCount = $state(0);
    let relaysConnected = $state(false);
    let showProfileMenu = $state(false);
    let isLoadingFolder = $state(false);

    let currentAccount = $derived(
        SharedStore.currentAccount !== "home"
            ? (SharedStore.currentAccount as Account)
            : SharedStore.accounts[0],
    );

    let accountInitial = $derived(
        SharedStore.accounts.length > 0
            ? (SharedStore.accounts[0].fullname || SharedStore.accounts[0].email_address)[0].toUpperCase()
            : "?",
    );

    let accountName = $derived(
        SharedStore.accounts.length > 0
            ? (SharedStore.accounts[0].fullname || SharedStore.accounts[0].email_address)
            : "No account",
    );

    let accountEmail = $derived(
        SharedStore.accounts.length > 0
            ? SharedStore.accounts[0].email_address
            : "",
    );

    let unreadCount = $derived.by(() => {
        const mailbox = SharedStore.mailboxes[currentAccount?.email_address ?? ""];
        if (!mailbox) return 0;
        return mailbox.emails.current.filter(
            (email) => !(email.flags ?? []).includes("\\Seen"),
        ).length;
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

    let relayPollInterval: ReturnType<typeof setInterval> | null = null;

    onMount(() => {
        fetchRelayStatus();
        relayPollInterval = setInterval(fetchRelayStatus, 30000);
        return () => { if (relayPollInterval) clearInterval(relayPollInterval); };
    });

    async function selectFolder(item: NavItem) {
        showView("inbox");
        MainNav.folder = item.folder ?? item.id;
        if (!item.folder || !currentAccount) return;
        isLoadingFolder = true;
        try {
            const response = await MailboxController.getMailbox(currentAccount, item.folder);
            if (!response.success) {
                showMessage({ title: local.error_get_mailbox[DEFAULT_LANGUAGE] });
            }
        } finally {
            isLoadingFolder = false;
        }
    }

    function selectView(item: NavItem) {
        if (item.folder) {
            selectFolder(item);
        } else {
            showView(item.view as MainView);
        }
    }

    async function toggleTheme() {
        const next: Theme = isDark ? Theme.Light : Theme.Dark;
        await PreferenceManager.changeTheme(next);
        isDark = !isDark;
        if (isDark) {
            document.documentElement.classList.add("dark");
        } else {
            document.documentElement.classList.remove("dark");
        }
    }

    function goToSettings() {
        showView("settings");
        showProfileMenu = false;
    }

    function closeProfileMenu() {
        showProfileMenu = false;
    }
</script>

<svelte:window onclick={() => { if (showProfileMenu) showProfileMenu = false; }} />

<aside class="w-64 flex-shrink-0 bg-notion-sidebar dark:bg-notion-sidebar-dark border-r border-notion-border dark:border-notion-border-dark flex flex-col justify-between h-full transition-all duration-200 z-20">
    <div>
        <!-- Window Controls -->
        <div class="p-3 pb-1">
            <div class="flex items-center space-x-2 mb-3 pl-1 pt-0.5">
                <span class="traffic-light bg-[#ff5f56]"></span>
                <span class="traffic-light bg-[#ffbd2e]"></span>
                <span class="traffic-light bg-[#27c93f]"></span>
            </div>

            <!-- Profile Switcher -->
            <div class="flex items-center justify-between group">
                <button
                    class="flex items-center space-x-2 hover:bg-notion-hover dark:hover:bg-notion-hover-dark p-1.5 rounded-md transition-colors text-left flex-1 min-w-0 mr-1"
                    onclick={(e) => { e.stopPropagation(); showProfileMenu = !showProfileMenu; }}
                >
                    <div class="w-6 h-6 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 flex items-center justify-center text-xs font-semibold flex-shrink-0">
                        {accountInitial}
                    </div>
                    <span class="font-medium text-sm text-gray-800 dark:text-gray-200 truncate">{accountName}</span>
                    <svg class="w-3.5 h-3.5 text-notion-text-muted flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>
                </button>

                <button
                    class="p-1.5 text-gray-600 dark:text-gray-300 hover:bg-notion-hover dark:hover:bg-notion-hover-dark rounded-md transition-colors"
                    title="Compose new message (N)"
                >
                    <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
                </button>
            </div>

            <!-- Profile Dropdown -->
            {#if showProfileMenu}
                <div class="absolute left-4 top-16 w-56 bg-white dark:bg-[#202020] rounded-lg shadow-lg border border-notion-border dark:border-notion-border-dark p-1.5 z-50 text-xs text-gray-700 dark:text-gray-200">
                    <div class="px-2 py-1.5 font-medium text-notion-text-muted border-b border-notion-border dark:border-notion-border-dark mb-1">
                        {accountEmail}
                    </div>
                    <button class="w-full text-left px-2 py-1.5 hover:bg-notion-hover dark:hover:bg-notion-hover-dark rounded flex items-center space-x-2" onclick={goToSettings}>
                        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                        <span>Account settings</span>
                    </button>
                    <button class="w-full text-left px-2 py-1.5 hover:bg-notion-hover dark:hover:bg-notion-hover-dark rounded flex items-center space-x-2" onclick={toggleTheme}>
                        {#if isDark}
                            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4"/></svg>
                        {:else}
                            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>
                        {/if}
                        <span>Toggle Dark Theme</span>
                    </button>
                    <div class="border-t border-notion-border dark:border-notion-border-dark my-1"></div>
                    <button class="w-full text-left px-2 py-1.5 hover:bg-notion-hover dark:hover:bg-notion-hover-dark rounded text-red-600 dark:text-red-400 flex items-center space-x-2">
                        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                        <span>Log out</span>
                    </button>
                </div>
            {/if}
        </div>

        <!-- Views Navigation -->
        <div class="px-2 pt-3 pb-1">
            <div class="px-2 py-1 text-[11px] font-semibold text-notion-text-muted uppercase tracking-wider">Views</div>
            <nav class="space-y-0.5 mt-0.5">
                {#each views as item}
                    <button
                        class="w-full flex items-center justify-between px-2.5 py-1.5 rounded-md text-sm transition-colors
                            {MainNav.view === 'inbox' && MainNav.folder === item.folder
                                ? 'bg-notion-active dark:bg-notion-active-dark font-medium text-gray-900 dark:text-white'
                                : 'text-gray-700 dark:text-gray-300 hover:bg-notion-hover dark:hover:bg-notion-hover-dark'}"
                        onclick={() => selectView(item)}
                    >
                        <div class="flex items-center space-x-2.5 min-w-0">
                            {#if item.icon === "inbox"}
                                <svg class="w-4 h-4 {MainNav.view === 'inbox' && MainNav.folder === item.folder ? 'text-red-500' : 'text-notion-text-muted'}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>
                            {:else if item.icon === "send"}
                                <svg class="w-4 h-4 text-notion-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                            {:else if item.icon === "file-edit"}
                                <svg class="w-4 h-4 text-notion-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
                            {/if}
                            <span class="truncate">{item.label}</span>
                        </div>
                        {#if item.id === "inbox" && unreadCount > 0}
                            <span class="text-xs text-notion-text-muted font-normal">{unreadCount}</span>
                        {/if}
                    </button>
                {/each}
            </nav>
        </div>

        <!-- Mail Section -->
        <div class="px-2 pt-3 pb-1">
            <div class="px-2 py-1 text-[11px] font-semibold text-notion-text-muted uppercase tracking-wider">Mail</div>
            <nav class="space-y-0.5 mt-0.5">
                {#each mailFolders as item}
                    <button
                        class="w-full flex items-center justify-between px-2.5 py-1.5 rounded-md text-sm text-gray-700 dark:text-gray-300 hover:bg-notion-hover dark:hover:bg-notion-hover-dark transition-colors"
                        onclick={() => selectView(item)}
                    >
                        <div class="flex items-center space-x-2.5 min-w-0">
                            {#if item.icon === "archive"}
                                <svg class="w-4 h-4 text-notion-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5" rx="1"/><line x1="10" y1="12" x2="14" y2="12"/></svg>
                            {:else if item.icon === "star"}
                                <svg class="w-4 h-4 text-notion-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                            {:else if item.icon === "lock"}
                                <svg class="w-4 h-4 text-notion-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                            {/if}
                            <span class="truncate">{item.label}</span>
                        </div>
                    </button>
                {/each}
            </nav>
        </div>
    </div>

    <!-- Sidebar Footer -->
    <div class="p-3 border-t border-notion-border dark:border-notion-border-dark flex items-center justify-between text-notion-text-muted">
        <div class="flex items-center space-x-1.5">
            <div class="text-[10px] font-semibold text-gray-700 dark:text-gray-300">
                {#if relaysConnected}
                    <span class="text-green-600 dark:text-green-400">{relayCount} relay{relayCount !== 1 ? 's' : ''}</span>
                {:else}
                    <span>offline</span>
                {/if}
            </div>
        </div>
        <button class="w-6 h-6 hover:bg-notion-hover dark:hover:bg-notion-hover-dark rounded flex items-center justify-center text-notion-text-muted hover:text-gray-800 dark:hover:text-gray-200 transition-colors" onclick={goToSettings} title="Settings">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.01a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z"/></svg>
        </button>
    </div>
</aside>
