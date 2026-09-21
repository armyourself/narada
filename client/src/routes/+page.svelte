<script lang="ts">
    import { SharedStore } from "$lib/stores/shared.svelte";
    import { MainNav } from "$lib/stores/mainNav.svelte";
    import { registry } from "$lib/ui/registry";
    import { getCurrentMailbox } from "$lib/ui/Layout/Main/Content/Mailbox.svelte";
    import Register from "$lib/ui/Layout/Landing/Register.svelte";
    import Welcome from "$lib/ui/Layout/Landing/Register/Welcome.svelte";
    import Accounts from "$lib/ui/Layout/Landing/Register/Accounts.svelte";
    import SetupServer from "$lib/ui/Layout/Landing/Register/SetupServer.svelte";

    const { layout, dashboard, views } = registry;

    let isConnectedToServer = $derived(SharedStore.server.length > 0);
    let isAnyAccountFound = $derived(SharedStore.accounts.length > 0 || SharedStore.failedAccounts.length > 0);
    let isMailboxInitialized = $derived(Object.keys(SharedStore.mailboxes).length > 0 && getCurrentMailbox());
</script>

{#if isMailboxInitialized}
    <layout.main>
        {#if MainNav.view === "inbox"}
            <dashboard.content />
        {:else if MainNav.view === "network"}
            <views.network />
        {:else if MainNav.view === "contacts"}
            <views.contacts />
        {:else if MainNav.view === "settings"}
            <views.settings />
        {/if}
    </layout.main>
{:else}
    <layout.landing>
        <Register>
            {#if isAnyAccountFound}
                <Accounts />
            {:else if isConnectedToServer}
                <Welcome/>
            {:else}
                <SetupServer/>
            {/if}
        </Register>
    </layout.landing>
{/if}
