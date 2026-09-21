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

<div class="layout-container" bind:this={sectionContainer}>
    {#if !isMounted}
        {@render children()}
    {/if}
</div>

<div class="modal-container" id="modal-container"></div>
<div class="toast-container" id="toast-container"></div>

<style>
    :global {
        .layout-container {
            position: relative;
            height: 100vh;
            width: 100vw;
            overflow: hidden;
        }
        .modal-container {
            position: fixed;
            display: none;
            align-items: center;
            justify-content: center;
            width: 100%;
            height: 100%;
            overflow: hidden;
            top: 0;
            left: 0;
            background-color: rgba(0, 0, 0, 0.4);
            backdrop-filter: blur(2px);
            z-index: 50;
        }
        body:has(.modal) .modal-container { display: flex; }
        .toast-container {
            position: fixed;
            bottom: 1.5rem;
            right: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            z-index: 50;
        }
    }
</style>
