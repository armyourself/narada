<script lang="ts">
    import "$lib/assets/style.css";
    import { onMount } from "svelte";
    import Layout from "$lib/ui/Layout/Layout.svelte";
    import Loading from "$lib/ui/Layout/Loading.svelte";
    import { SharedStore } from "$lib/stores/shared.svelte";
    import { show as showConfirm } from "$lib/ui/Components/Confirm";
    import { getCurrentWindow } from '@tauri-apps/api/window';
    import { PreferenceStore, Theme } from "$lib/preferences";

    const appWindow = getCurrentWindow();

    let { children } = $props();

    let isAppLoaded = $derived(SharedStore.isAppLoaded);

    onMount(() => {
        appWindow.onThemeChanged(async ({ payload: theme }) => {
            if (PreferenceStore.theme === Theme.System || !PreferenceStore.theme) {
                const newTheme = theme.toLowerCase();
                if (newTheme === "dark") {
                    document.documentElement.classList.add("dark");
                } else {
                    document.documentElement.classList.remove("dark");
                }
                localStorage.setItem("theme", newTheme);
            }
        });
    });
</script>

<Layout>
    {#if !isAppLoaded}
        <Loading />
    {:else}
        {@render children()}
    {/if}
</Layout>

<div class="modal-container" id="modal-container"></div>
<div class="toast-container" id="toast-container"></div>

<style>
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
</style>
