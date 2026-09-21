<script lang="ts">
    import type { Snippet } from "svelte";
    import Sidebar from "./Main/Sidebar.svelte";

    interface Props {
        children: Snippet;
    }

    let { children }: Props = $props();
</script>

<div class="flex h-full w-full">
    <Sidebar />
    <main class="flex-1 flex flex-col h-full bg-white dark:bg-[#121212] overflow-hidden relative">
        {@render children()}
    </main>
</div>
