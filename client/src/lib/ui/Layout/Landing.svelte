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
    import { DEFAULT_LANGUAGE } from "$lib/constants";
    import Background from "./Background.svelte";

    interface Props {
        children: Snippet;
    }

    let { children }: Props = $props();
</script>

<Background />

<section class="landing-container" bind:this={sectionContainer}>
    <div class="landing-header">
        <h1 class="logo">Narada</h1>
        <p class="landing-subtitle">
            Decentralized email with end-to-end encryption
        </p>
    </div>
    <div class="landing-body">
        {#if !isMounted}
            {@render children()}
        {/if}
    </div>
</section>

<style>
    :global {
        .landing-container {
            position: relative;
            z-index: 1;
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
        }

        .landing-header {
            text-align: center;
        }

        .landing-header .logo {
            font-family: var(--ui);
            font-weight: 600;
            font-size: 1.8rem;
            margin-bottom: var(--spacing-xs);
            color: var(--ink);
        }

        .landing-subtitle {
            margin-bottom: var(--spacing-xl);
            font-size: var(--font-size-sm);
            text-align: center;
            color: var(--ink-dim);
        }

        .landing-body {
            width: var(--container-md);
            background: var(--glass);
            backdrop-filter: blur(18px) saturate(1.4);
            -webkit-backdrop-filter: blur(18px) saturate(1.4);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius);
            box-shadow: var(--shadow);
            padding: var(--spacing-lg);
        }

        .landing-body-footer {
            display: flex;
            flex-direction: column;
            gap: var(--spacing-lg);
            text-align: center;
            margin-top: var(--spacing-2xl);
        }
    }
</style>
