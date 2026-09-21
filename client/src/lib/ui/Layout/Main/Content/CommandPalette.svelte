<script lang="ts">
    interface Props {
        onClose: () => void;
    }

    let { onClose }: Props = $props();
    let query = $state("");
    let inputEl: HTMLInputElement | undefined = $state();

    interface Command {
        label: string;
        icon: string;
        shortcut?: string;
        category: string;
    }

    const commands: Command[] = [
        { label: "Close thread", icon: "x-square", shortcut: "Escape", category: "Thread" },
        { label: "Previous thread", icon: "arrow-left", shortcut: "K", category: "Thread" },
        { label: "Next thread", icon: "arrow-right", shortcut: "J", category: "Thread" },
        { label: "Mark as unread", icon: "mail", shortcut: "Shift+U", category: "Thread" },
        { label: "Mark as read or unread", icon: "check-square", shortcut: "U", category: "Thread" },
        { label: "Forward", icon: "corner-up-right", shortcut: "F", category: "Thread" },
        { label: "Reply", icon: "corner-up-left", shortcut: "R", category: "Thread" },
        { label: "Reply all", icon: "reply-all", shortcut: "A", category: "Thread" },
    ];

    let filtered = $derived(
        query.trim()
            ? commands.filter(c => c.label.toLowerCase().includes(query.toLowerCase()))
            : commands
    );

    let grouped = $derived.by(() => {
        const cats: Record<string, Command[]> = {};
        filtered.forEach(c => {
            if (!cats[c.category]) cats[c.category] = [];
            cats[c.category].push(c);
        });
        return cats;
    });

    function handleKeydown(e: KeyboardEvent) {
        if (e.key === "Escape") onClose();
    }

    function selectIcon(icon: string): string {
        const icons: Record<string, string> = {
            "x-square": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="m9 9 6 6"/><path d="m15 9-6 6"/>',
            "arrow-left": '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
            "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
            "mail": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
            "check-square": '<polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
            "corner-up-right": '<polyline points="15 14 20 9 15 4"/><path d="M4 20v-7a4 4 0 0 1 4-4h12"/>',
            "corner-up-left": '<polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/>',
            "reply-all": '<polyline points="7 17 2 12 7 7"/><polyline points="12 17 7 12 12 7"/><path d="M22 18v-2a4 4 0 0 0-4-4H7"/>',
        };
        return icons[icon] || "";
    }
</script>

<svelte:window on:keydown={handleKeydown} />

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="fixed inset-0 bg-black/40 backdrop-blur-xs z-50 flex items-start justify-center pt-20 px-4 transition-opacity" on:click={onClose}>
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="bg-white dark:bg-[#1e1e1e] w-full max-w-xl rounded-xl shadow-2xl border border-notion-border dark:border-notion-border-dark overflow-hidden flex flex-col command-modal-shadow transform transition-all duration-150" on:click|stopPropagation>
        <!-- Input -->
        <div class="flex items-center px-4 py-3 border-b border-notion-border dark:border-notion-border-dark">
            <svg class="w-4 h-4 text-notion-text-muted mr-3 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
            <input
                bind:this={inputEl}
                bind:value={query}
                type="text"
                placeholder="Search commands or Narada..."
                class="w-full bg-transparent text-sm text-gray-800 dark:text-gray-100 placeholder-notion-text-muted focus:outline-none"
            />
        </div>

        <!-- Command List -->
        <div class="max-h-96 overflow-y-auto p-1 space-y-1">
            {#each Object.entries(grouped) as [category, items]}
                <div class="px-3 py-1.5 text-[11px] font-semibold text-notion-text-muted uppercase tracking-wider">{category}</div>
                {#each items as cmd}
                    <button class="w-full flex items-center justify-between px-3 py-2 rounded-md hover:bg-notion-hover dark:hover:bg-notion-hover-dark text-left group" on:click={onClose}>
                        <div class="flex items-center space-x-3">
                            <svg class="w-4 h-4 text-notion-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{@html selectIcon(cmd.icon)}</svg>
                            <span class="text-sm font-normal text-gray-800 dark:text-gray-200">{cmd.label}</span>
                        </div>
                        {#if cmd.shortcut}
                            <kbd class="text-xs text-notion-text-muted font-sans">{cmd.shortcut}</kbd>
                        {/if}
                    </button>
                {/each}
            {/each}
        </div>

        <!-- Footer -->
        <div class="px-4 py-2 border-t border-notion-border dark:border-notion-border-dark bg-gray-50/50 dark:bg-[#1a1a1a] flex items-center justify-start space-x-4 text-xs text-notion-text-muted">
            <span class="flex items-center">
                <svg class="w-3 h-3 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/></svg>
                Select
            </span>
            <span class="flex items-center">
                <svg class="w-3 h-3 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
                Open
            </span>
        </div>
    </div>
</div>
