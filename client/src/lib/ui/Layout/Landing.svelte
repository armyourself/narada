<script module lang="ts">
    import { mount, unmount } from "svelte";
    import { type Snippet } from "svelte";

    let sectionContainer: HTMLElement;
    let isMounted = $state(false);
    let currentMount: Record<string, any> | null = null;

    export function showThis(section: any, props?: any) {
        isMounted = true;
        clear();
        currentMount = mount(section, {
            target: sectionContainer,
            props: props
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
    interface Props {
        children: Snippet;
    }

    let { children }: Props = $props();
</script>

<section class="flex items-center justify-center w-full h-full flex-col" bind:this={sectionContainer}>
    <div class="text-center mb-8">
        <h1 class="text-2xl font-semibold text-gray-900 dark:text-white mb-1">Narada</h1>
        <p class="text-sm text-notion-text-muted">
            Decentralized email with end-to-end encryption
        </p>
    </div>
    <div class="w-[480px] bg-white dark:bg-[#1e1e1e] border border-notion-border dark:border-notion-border-dark rounded-xl shadow-lg p-6">
        {#if !isMounted}
            {@render children()}
        {/if}
    </div>
</section>
