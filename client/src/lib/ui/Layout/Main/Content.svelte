<script module lang="ts">
    import { mount, unmount } from "svelte";

    /**
     * Detail-area router for the main dashboard.
     *
     * `showThis(component)` renders `component` into the detail panel
     * (the Email reading view or the Compose editor). The mail list
     * stays mounted in the list panel at all times; `showThis(Mailbox)`
     * and `backToDefault()` merely clear the detail view.
     */
    let detailMount: HTMLElement | undefined = $state();
    let isMounted = $state(false);
    let currentMount: Record<string, any> | null = null;

    let mailboxSection: any = null;

    export function registerMailbox(section: any) {
        mailboxSection = section;
    }

    export function showThis(section: any, props?: any) {
        if (!detailMount) return;
        clear();
        if (section === mailboxSection) {
            isMounted = false;
            return;
        }
        isMounted = true;
        currentMount = mount(section, {
            target: detailMount,
            props: props,
        });
    }

    export function backToDefault() {
        clear();
        isMounted = false;
    }

    function clear() {
        if (currentMount) unmount(currentMount);
        currentMount = null;
    }
</script>

<script lang="ts">
    import { onMount } from "svelte";
    import Mailbox from "./Content/Mailbox.svelte";

    let detailPanel: HTMLElement | undefined = $state();

    onMount(() => {
        registerMailbox(Mailbox);
    });

    // Module-level `detailMount` must track the bound element; a plain
    // bind:this in the instance script only updates the instance copy.
    $effect(() => {
        detailMount = detailPanel;
    });
</script>

<div class="content-region">
    <div class="list-panel">
        <Mailbox />
    </div>
    <div class="detail-panel" bind:this={detailPanel}>
        {#if !isMounted}
            <div class="empty-state">
                <svg viewBox="0 0 24 24"><path d="M3 8l9 6 9-6"/><rect x="3" y="5" width="18" height="14" rx="2"/></svg>
                <p>Select a message to read it. Nothing here ever passes through a server that can see it in plaintext.</p>
            </div>
        {/if}
    </div>
</div>

<style>
    :global {
        .content-region {
            flex-grow: 1;
            display: flex;
            min-width: 0;
        }

        .list-panel {
            width: 330px;
            border-right: 1px solid var(--glass-border);
            background: var(--glass-solid);
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
        }

        .detail-panel {
            flex-grow: 1;
            background: var(--cream);
            display: flex;
            flex-direction: column;
            overflow-y: auto;
            min-width: 0;
            position: relative;
            padding: 28px 36px;
        }

        .detail-panel .empty-state {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            color: var(--ink-faint);
            gap: 12px;
            text-align: center;
        }

        .detail-panel .empty-state svg {
            width: 2.2rem;
            height: 2.2rem;
            stroke: var(--ink-faint);
            fill: none;
            stroke-width: 1.5;
            stroke-linecap: round;
            stroke-linejoin: round;
            opacity: 0.6;
        }

        .detail-panel .empty-state p {
            font-size: 0.85rem;
            max-width: 28ch;
        }
    }
</style>
