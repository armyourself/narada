<script lang="ts">
    import { SharedStore } from "$lib/stores/shared.svelte";
    import { DEFAULT_LANGUAGE } from "$lib/constants";
    import { local } from "$lib/locales";
    import { MailboxController } from "$lib/mailbox";

    let currentFolder = $state("inbox");

    const folders = [
        { id: "inbox", label: "Inbox", icon: '<path d="M3 12h4l2 4h6l2-4h4"/><path d="M5 5h14l2 7v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-6l2-7Z"/>' },
        { id: "starred", label: "Starred", icon: '<path d="M12 3l2.6 5.9 6.4.6-4.8 4.3 1.4 6.3L12 17l-5.6 3.1 1.4-6.3-4.8-4.3 6.4-.6L12 3Z"/>' },
        { id: "sent", label: "Sent", icon: '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7Z"/>' },
        { id: "drafts", label: "Drafts", icon: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>' },
        { id: "all", label: "All mail", icon: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 8h18"/>' },
    ];

    const extraFolders = [
        { id: "encrypted", label: "Encrypted", icon: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>' },
        { id: "network", label: "Node network", icon: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8 7.5 10.5 15.5M16 7.5 13.5 15.5M8.5 6h7"/>' },
        { id: "trash", label: "Trash", icon: '<path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>' },
    ];

    function selectFolder(id: string) {
        currentFolder = id;
    }

    let naradaId = $derived(
        SharedStore.accounts.length > 0
            ? `narada1q${SharedStore.accounts[0].email_address.slice(0, 6)}...`
            : "narada1q...not set"
    );
</script>

<aside class="sidebar">
    <div class="sidebar-header">
        <span class="panel-title">Menu</span>
    </div>
    <div class="sidebar-body">
        <button class="compose-btn" title="Compose">
            <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
            <span>Compose</span>
        </button>

        <div class="nav-group">
            {#each folders as folder}
                <button
                    class="nav-item"
                    class:active={currentFolder === folder.id}
                    onclick={() => selectFolder(folder.id)}
                    title={folder.label}
                >
                    <span class="left">
                        <svg viewBox="0 0 24 24">{@html folder.icon}</svg>
                        <span class="label-text">{folder.label}</span>
                    </span>
                </button>
            {/each}
        </div>

        <div class="nav-group">
            {#each extraFolders as folder}
                <button
                    class="nav-item"
                    class:active={currentFolder === folder.id}
                    onclick={() => selectFolder(folder.id)}
                    title={folder.label}
                >
                    <span class="left">
                        <svg viewBox="0 0 24 24">{@html folder.icon}</svg>
                        <span class="label-text">{folder.label}</span>
                    </span>
                </button>
            {/each}
        </div>
    </div>

    <div class="sidebar-foot">
        <div class="node-id">
            <span class="id-label">your node</span>
            <span class="id-val">{naradaId}</span>
        </div>
    </div>
</aside>

<style>
    :global {
        .sidebar {
            position: absolute;
            top: 88px;
            left: 22px;
            bottom: 22px;
            width: 232px;
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

        .sidebar .sidebar-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px 16px;
            border-bottom: 1px solid var(--glass-border);
            flex-shrink: 0;
        }

        .sidebar .sidebar-header .panel-title {
            font-family: var(--ui);
            font-size: 0.72rem;
            font-weight: 600;
            color: var(--ink-dim);
            letter-spacing: 0.02em;
        }

        .sidebar .sidebar-body {
            flex: 1;
            overflow-y: auto;
            padding: 12px 14px 16px;
        }

        .compose-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            background: var(--glass-strong);
            border: 1px solid var(--glass-border);
            color: var(--ink);
            font-family: var(--ui);
            font-weight: 600;
            font-size: 0.86rem;
            padding: 12px 18px;
            border-radius: var(--radius-sm);
            box-shadow: 0 4px 14px rgba(203, 154, 115, 0.20);
            transition: transform 0.18s ease, box-shadow 0.18s ease;
            margin-bottom: 18px;
            width: 100%;
        }

        .compose-btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 8px 20px rgba(203, 154, 115, 0.28);
        }

        .compose-btn svg {
            width: 17px;
            height: 17px;
            stroke: var(--accent);
            fill: none;
            stroke-width: 2.2;
            stroke-linecap: round;
            flex-shrink: 0;
        }

        .nav-group {
            display: flex;
            flex-direction: column;
            gap: 2px;
            margin-bottom: 16px;
        }

        .nav-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            padding: 9px 11px;
            border-radius: var(--radius-sm);
            font-size: 0.85rem;
            color: var(--ink-dim);
            border-left: 2px solid transparent;
            transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
            cursor: pointer;
            text-align: left;
            width: 100%;
        }

        .nav-item .left {
            display: flex;
            align-items: center;
            gap: 11px;
            min-width: 0;
        }

        .nav-item .label-text {
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .nav-item svg {
            width: 16px;
            height: 16px;
            stroke: currentColor;
            fill: none;
            stroke-width: 2;
            flex-shrink: 0;
        }

        .nav-item:hover {
            background: var(--glass-strong);
            color: var(--ink);
        }

        .nav-item.active {
            background: var(--glass-strong);
            color: var(--ink);
            font-weight: 600;
            border-left-color: var(--accent);
        }

        .nav-item.active .left svg {
            stroke: var(--accent);
        }

        .sidebar-foot {
            margin-top: auto;
            padding: 14px 16px;
            border-top: 1px solid var(--glass-border);
        }

        .node-id {
            font-family: var(--ui);
            font-size: 0.66rem;
            color: var(--ink-faint);
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .node-id .id-val {
            color: var(--ink-dim);
            word-break: break-all;
        }

        .node-id .id-label {
            letter-spacing: 0.02em;
        }
    }
</style>
