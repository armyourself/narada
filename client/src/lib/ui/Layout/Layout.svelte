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
    import Titlebar from "./Titlebar.svelte";
    import Background from "./Background.svelte";

    interface Props {
        children: Snippet;
    }

    let { children }: Props = $props();
</script>

<Background />
<Titlebar/>

<div class="layout-container" bind:this={sectionContainer}>
    {#if !isMounted}
        {@render children()}
    {/if}
</div>

<style>
    :global {
        .layout-container {
            position: relative;
            z-index: 1;
            height: 100vh;
            width: 100vw;
            padding: 18px 22px 22px;
            padding-top: 88px;
            overflow: hidden;
        }

        .alert-container {
            display: flex;
            flex-direction: column-reverse;
            margin-bottom: var(--spacing-md);
        }
        .alert-container:empty { display: none; }
    }
</style>
