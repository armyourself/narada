<script module lang="ts">
    import { mount, unmount } from "svelte";

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

    $effect(() => {
        detailMount = detailPanel;
    });
</script>

<div class="flex-1 flex flex-col h-full overflow-hidden">
    <Mailbox />
    <div bind:this={detailPanel} class="hidden"></div>
</div>
