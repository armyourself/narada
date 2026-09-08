<script lang="ts">
    import Operations from "$lib/ui/Layout/Main/Content/Mailbox/Toolbox/Operations.svelte";
    import Pagination from "$lib/ui/Layout/Main/Content/Mailbox/Toolbox/Pagination.svelte";
    import { getCurrentMailbox } from "$lib/ui/Layout/Main/Content/Mailbox.svelte";
    import { SharedStore } from "$lib/stores/shared.svelte";

    let totalEmails = $derived(getCurrentMailbox().total);
</script>

<div class="list-head">
    <span class="panel-title">Inbox</span>
    <span class="sub">{totalEmails} conversation{totalEmails !== 1 ? 's' : ''}</span>
</div>

<style>
    :global {
        .list-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px 16px;
            border-bottom: 1px solid var(--glass-border);
            flex-shrink: 0;
        }

        .list-head .panel-title {
            font-family: var(--ui);
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--ink);
        }

        .list-head .sub {
            font-family: var(--body);
            font-weight: 400;
            font-size: 0.72rem;
            color: var(--ink-faint);
        }
    }
</style>
