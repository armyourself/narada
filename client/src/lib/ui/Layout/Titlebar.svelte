<script lang="ts">
    import { getCurrentWindow } from '@tauri-apps/api/window';
    import { onMount } from "svelte";
    import { SharedStore } from "$lib/stores/shared.svelte";

    const appWindow = getCurrentWindow();

    onMount(() => {
        document.getElementById('titlebar-minimize')!
            .addEventListener('click', () => appWindow.minimize());
        document.getElementById('titlebar-maximize')!
            .addEventListener('click', () => appWindow.toggleMaximize());
        document.getElementById('titlebar-close')!
            .addEventListener('click', () => appWindow.close());
    });

    let accountInitial = $derived(
        SharedStore.accounts.length > 0
            ? (SharedStore.accounts[0].fullname || SharedStore.accounts[0].email_address)[0].toUpperCase()
            : "?"
    );
</script>

<div data-tauri-drag-region class="topbar">
    <div class="brand">Narada</div>

    <div class="search">
        <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
        <input type="text" placeholder="Search mail" />
    </div>

    <div class="topbar-right">
        <div class="peer-pill"><span class="live"></span>6 peers</div>

        <button class="icon-btn" id="titlebar-minimize" title="Minimize">
            <svg viewBox="0 0 24 24"><path d="M5 12h14"/></svg>
        </button>
        <button class="icon-btn" id="titlebar-maximize" title="Maximize">
            <svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>
        </button>
        <button class="icon-btn" id="titlebar-close" title="Close">
            <svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>

        <div class="avatar">{accountInitial}</div>
    </div>
</div>

<style>
    :global {
        .topbar {
            position: fixed;
            top: 18px;
            left: 22px;
            right: 22px;
            z-index: var(--z-index-titlebar);
            display: flex;
            align-items: center;
            gap: 18px;
            background: var(--glass);
            backdrop-filter: blur(18px) saturate(1.4);
            -webkit-backdrop-filter: blur(18px) saturate(1.4);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius);
            padding: 10px 18px;
            box-shadow: var(--shadow);
            height: auto;
        }

        .topbar .brand {
            display: flex;
            align-items: center;
            gap: 9px;
            font-family: var(--ui);
            font-weight: 600;
            font-size: 1.02rem;
            white-space: nowrap;
            padding-right: 6px;
            color: var(--ink);
        }

        .topbar .search {
            flex: 1;
            display: flex;
            align-items: center;
            gap: 10px;
            background: var(--glass-strong);
            border: 1px solid var(--glass-border);
            border-radius: 100px;
            padding: 9px 16px;
            max-width: 560px;
            color: var(--ink-dim);
        }

        .topbar .search svg {
            width: 16px;
            height: 16px;
            flex-shrink: 0;
            stroke: var(--ink-dim);
            fill: none;
            stroke-width: 2;
        }

        .topbar .search input {
            background: none;
            border: none;
            outline: none;
            flex: 1;
            font-size: 0.87rem;
            color: var(--ink);
        }

        .topbar .search input::placeholder { color: var(--ink-faint); }

        .topbar-right {
            display: flex;
            align-items: center;
            gap: 14px;
            margin-left: auto;
        }

        .peer-pill {
            display: flex;
            align-items: center;
            gap: 7px;
            font-family: var(--ui);
            font-size: 0.68rem;
            color: var(--ink-dim);
            background: var(--glass-strong);
            border: 1px solid var(--glass-border);
            padding: 6px 12px;
            border-radius: 100px;
            white-space: nowrap;
        }

        .peer-pill .live {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #7CBF9E;
        }

        .icon-btn {
            width: 34px;
            height: 34px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--ink-dim);
            flex-shrink: 0;
            transition: background 0.15s, color 0.15s;
        }

        .icon-btn:hover {
            background: var(--glass-strong);
            color: var(--ink);
        }

        .icon-btn svg {
            width: 17px;
            height: 17px;
            stroke: currentColor;
            fill: none;
            stroke-width: 1.9;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        .avatar {
            width: 34px;
            height: 34px;
            border-radius: 50%;
            background: linear-gradient(145deg, var(--accent-soft), var(--accent));
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            font-family: var(--ui);
            font-weight: 600;
            font-size: 0.8rem;
            flex-shrink: 0;
        }
    }
</style>
