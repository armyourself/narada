<script lang="ts">
    import { onMount } from "svelte";
    import { MainNav, showView, type MainView } from "$lib/stores/mainNav.svelte";
    import { SharedStore } from "$lib/stores/shared.svelte";
    import { PreferenceManager, Theme } from "$lib/preferences";

    interface RailButton {
        view: MainView;
        title: string;
        icon: string;
    }

    const railButtons: RailButton[] = [
        { view: "inbox", title: "Mail", icon: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>' },
        { view: "network", title: "Node network", icon: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8.5 6h7"/><path d="M8 7.5 10.5 15.5"/><path d="M16 7.5 13.5 15.5"/>' },
        { view: "contacts", title: "Contacts", icon: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"/>' },
        { view: "settings", title: "Settings", icon: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.01a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z"/>' },
    ];

    let accountInitial = $derived(
        SharedStore.accounts.length > 0
            ? (SharedStore.accounts[0].fullname || SharedStore.accounts[0].email_address)[0].toUpperCase()
            : "?",
    );

    let isDark = $state(
        typeof document !== "undefined" &&
            document.documentElement.getAttribute("data-color-scheme") === "dark",
    );

    onMount(() => {
        // data-color-scheme is mutated by the theme toggle, the Settings
        // page, and the Tauri system-theme listener; observe it so the
        // rail icon always reflects the applied theme.
        const observer = new MutationObserver(() => {
            isDark =
                document.documentElement.getAttribute("data-color-scheme") === "dark";
        });
        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["data-color-scheme"],
        });
        return () => observer.disconnect();
    });

    async function toggleTheme() {
        const next: Theme = isDark ? Theme.Light : Theme.Dark;
        // Writing the preference applies the DOM attribute and persists it;
        // this intentionally switches the user off "System" onto a fixed side.
        await PreferenceManager.changeTheme(next);
    }
</script>

<div class="rail">
    <div class="logo">
        <svg viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>
    </div>

    <div class="nav-icons">
        {#each railButtons as btn}
            <button
                class:active={MainNav.view === btn.view}
                onclick={() => showView(btn.view)}
                title={btn.title}
                aria-label={btn.title}
            >
                <svg viewBox="0 0 24 24">{@html btn.icon}</svg>
            </button>
        {/each}
    </div>

    <div class="rail-foot">
        <button class="theme-btn" onclick={toggleTheme} title="Toggle theme" aria-label="Toggle theme">
            {#if isDark}
                <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4"/></svg>
            {:else}
                <svg viewBox="0 0 24 24"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>
            {/if}
        </button>
        <div class="profile-pic" title={SharedStore.accounts[0]?.email_address ?? ""}>{accountInitial}</div>
    </div>
</div>

<style>
    :global {
        .rail {
            width: 74px;
            border-right: 1px solid var(--glass-border);
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 26px 0;
            background: var(--glass-strong);
            flex-shrink: 0;
        }

        .rail .logo {
            width: 34px;
            height: 34px;
            border-radius: 10px;
            background: linear-gradient(145deg, var(--accent-soft), var(--accent));
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            margin-bottom: 36px;
            flex-shrink: 0;
        }

        .rail .logo svg {
            width: 16px;
            height: 16px;
            stroke: #fff;
            fill: none;
            stroke-width: 2.2;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        .rail .nav-icons {
            display: flex;
            flex-direction: column;
            gap: 26px;
            flex-grow: 1;
            align-items: center;
        }

        .rail .nav-icons button {
            width: 40px;
            height: 40px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--ink-faint);
            transition: background 0.15s, color 0.15s;
        }

        .rail .nav-icons button:hover {
            background: var(--glass-solid);
            color: var(--ink);
        }

        .rail .nav-icons button.active {
            background: var(--glass-solid);
            color: var(--accent);
            box-shadow: inset 0 0 0 1px var(--glass-border);
        }

        .rail .nav-icons button svg {
            width: 18px;
            height: 18px;
            stroke: currentColor;
            fill: none;
            stroke-width: 1.9;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        .rail .rail-foot {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 16px;
        }

        .rail .theme-btn {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--ink-faint);
        }

        .rail .theme-btn:hover {
            background: var(--glass-solid);
            color: var(--ink);
        }

        .rail .theme-btn svg {
            width: 15px;
            height: 15px;
            stroke: currentColor;
            fill: none;
            stroke-width: 2;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        .rail .profile-pic {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            background: linear-gradient(145deg, var(--accent-soft), var(--accent));
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            font-family: var(--ui);
            font-weight: 600;
            font-size: 0.75rem;
        }
    }
</style>
