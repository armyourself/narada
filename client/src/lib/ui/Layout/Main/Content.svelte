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
    import { SharedStore } from "$lib/stores/shared.svelte";
    import { local } from "$lib/locales";
    import { DEFAULT_LANGUAGE } from "$lib/constants";

    interface Props {
        children: Snippet;
    }

    let { children }: Props = $props();
</script>

<div class="content" bind:this={sectionContainer}>
    {#if !isMounted}
        {@render children()}
    {/if}
</div>

<style>
    :global {
        .content {
            position: absolute;
            top: 88px;
            left: 268px;
            bottom: 22px;
            width: 380px;
            z-index: 2;
            background: var(--glass);
            backdrop-filter: blur(18px) saturate(1.4);
            -webkit-backdrop-filter: blur(18px) saturate(1.4);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius);
            box-shadow: var(--shadow);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
    }
</style>
