<script lang="ts">
    import { SharedStore } from "$lib/stores/shared.svelte";
    import { MainNav } from "$lib/stores/mainNav.svelte";
    import Main from "$lib/ui/Layout/Main.svelte";
    import Content from "$lib/ui/Layout/Main/Content.svelte";
    import { getCurrentMailbox } from "$lib/ui/Layout/Main/Content/Mailbox.svelte";
    import Network from "$lib/ui/Layout/Main/Views/Network.svelte";
    import Contacts from "$lib/ui/Layout/Main/Views/Contacts.svelte";
    import Settings from "$lib/ui/Layout/Main/Views/Settings.svelte";
    import Landing from "$lib/ui/Layout/Landing.svelte";
    import Register from "$lib/ui/Layout/Landing/Register.svelte";
    import Welcome from "$lib/ui/Layout/Landing/Register/Welcome.svelte";
    import Accounts from "$lib/ui/Layout/Landing/Register/Accounts.svelte";
    import SetupServer from "$lib/ui/Layout/Landing/Register/SetupServer.svelte";

    let isConnectedToServer = $derived(SharedStore.server.length > 0);
    let isAnyAccountFound = $derived(SharedStore.accounts.length > 0 || SharedStore.failedAccounts.length > 0);
    let isMailboxInitialized = $derived(Object.keys(SharedStore.mailboxes).length > 0 && getCurrentMailbox());
</script>

{#if isMailboxInitialized}
    <Main>
        {#if MainNav.view === "inbox"}
            <Content />
        {:else if MainNav.view === "network"}
            <Network />
        {:else if MainNav.view === "contacts"}
            <Contacts />
        {:else if MainNav.view === "settings"}
            <Settings />
        {/if}
    </Main>
{:else}
    <Landing>
        <Register>
            {#if isAnyAccountFound}
                <Accounts />
            {:else if isConnectedToServer}
                <Welcome/>
            {:else}
                <SetupServer/>
            {/if}
        </Register>
    </Landing>
{/if}
