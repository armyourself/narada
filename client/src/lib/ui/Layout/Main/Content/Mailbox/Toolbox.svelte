<script lang="ts">
    import Operations from "$lib/ui/Layout/Main/Content/Mailbox/Toolbox/Operations.svelte";
    import Pagination from "$lib/ui/Layout/Main/Content/Mailbox/Toolbox/Pagination.svelte";
    import { getCurrentMailbox } from "$lib/ui/Layout/Main/Content/Mailbox.svelte";
    import { MainNav } from "$lib/stores/mainNav.svelte";

    const folderLabels: Record<string, string> = {
        inbox: "Inbox",
        starred: "Starred",
        sent: "Sent",
        drafts: "Drafts",
        all: "All mail",
        encrypted: "Encrypted",
        network: "Node network",
        trash: "Trash",
    };

    let totalEmails = $derived(getCurrentMailbox().total);
    let folderTitle = $derived(folderLabels[MainNav.folder] ?? "Inbox");
</script>

<div class="list-head">
    <span class="panel-title">{folderTitle}</span>
    <span class="sub">{totalEmails} conversation{totalEmails !== 1 ? 's' : ''}</span>
</div>

<style>
    :global {
        .list-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 14px 20px 4px;
            flex-shrink: 0;
        }

        .list-head .panel-title {
            font-family: var(--ui);
            font-size: 0.9rem;
            font-weight: 600;
            color: var(--ink);
        }

        .list-head .sub {
            font-family: var(--body);
            font-weight: 400;
            font-size: 0.68rem;
            color: var(--ink-faint);
        }
    }
</style>
