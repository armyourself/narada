<script lang="ts">
    import type { Snippet } from "svelte";
    import Rail from "./Main/Rail.svelte";
    import Menu from "./Main/Menu.svelte";

    interface Props {
        children: Snippet;
    }

    let { children }: Props = $props();
</script>

<div class="dashboard">
    <Rail />
    <Menu />
    {@render children()}
</div>

<style>
    :global {
        .dashboard {
            position: relative;
            z-index: 1;
            background: var(--glass);
            backdrop-filter: blur(24px) saturate(1.4);
            -webkit-backdrop-filter: blur(24px) saturate(1.4);
            width: 100vw;
            height: 100vh;
            display: flex;
            overflow: hidden;
            transition: background 0.4s ease, border-color 0.4s ease;
        }
    }
</style>
