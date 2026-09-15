<script lang="ts">
    import { SharedStore } from "$lib/stores/shared.svelte";
    import { naradaIdentity } from "$lib/narada/identity.svelte";
    import { show as showToast } from "$lib/ui/Components/Toast";
    import type { Account } from "$lib/types";

    interface PeerRow {
        status: "up" | "down";
        name: string;
        addr: string;
        meta: string;
    }

    let bootstrapInput = $state("");

    let nodeId = $derived(
        naradaIdentity.state.publicId ?? "no identity on this account",
    );

    let accounts = $derived(SharedStore.accounts);

    /**
     * Server-reachable accounts. The node daemon has no peer-list HTTP
     * API yet, so "peers" here are the mailbox accounts the daemon
     * reports it can talk to; everything else in this view is stubbed
     * until the QUIC PeerBook is exposed over HTTP (Phase 6).
     */
    let peers = $derived.by(() => {
        const rows: PeerRow[] = accounts.map((account) => ({
            status: "up",
            name: account.fullname || account.email_address,
            addr: account.email_address,
            meta: "server reachable",
        }));
        SharedStore.failedAccounts.forEach((account) => {
            rows.push({
                status: "down",
                name: account.fullname || account.email_address,
                addr: account.email_address,
                meta: "unreachable",
            });
        });
        return rows;
    });

    let upCount = $derived(peers.filter((p) => p.status === "up").length);
    let downCount = $derived(peers.filter((p) => p.status === "down").length);

    async function copyNodeId() {
        try {
            await navigator.clipboard.writeText(nodeId);
            showToast({ content: "node id copied" });
        } catch {
            /* clipboard unavailable (e.g. insecure context) — ignore */
        }
    }

    function addBootstrap() {
        const value = bootstrapInput.trim();
        if (!value) return;
        // The daemon does not accept bootstrap peers over HTTP yet.
        showToast({
            content: "bootstrap peers need the node API — not wired yet",
        });
        bootstrapInput = "";
    }
</script>

<div class="settings-panel active">
    <div class="settings-title">Node network</div>
    <div class="settings-sub">Who your node is talking to right now.</div>

    <div class="settings-section">
        <h3>Your node</h3>
        <div class="settings-node-id">
            <span>{nodeId}</span>
            <button onclick={copyNodeId} title="Copy" aria-label="Copy node id">
                <svg viewBox="0 0 24 24"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            </button>
        </div>
        <div class="settings-row">
            <div>
                <div class="settings-row-label">Status</div>
                <div class="settings-row-desc">Listening on QUIC, discoverable via mDNS.</div>
            </div>
            <div class="tag"><span class="status-dot up"></span>Online</div>
        </div>
    </div>

    <div class="settings-section">
        <h3>Network health</h3>
        <div class="stat-row">
            <div class="stat"><span class="stat-num">{peers.length}</span><span class="stat-label">peers connected</span></div>
            <div class="stat"><span class="stat-num">{upCount}</span><span class="stat-label">reachable</span></div>
            <div class="stat"><span class="stat-num">0</span><span class="stat-label">relayed</span></div>
            <div class="stat"><span class="stat-num">{downCount}</span><span class="stat-label">down</span></div>
        </div>
    </div>

    <div class="settings-section">
        <h3>Connected peers</h3>
        {#if peers.length === 0}
            <div class="empty-note">No peers yet — the node reports no reachable accounts.</div>
        {:else}
            <div class="peer-list">
                {#each peers as peer}
                    <div class="peer-row">
                        <span class="status-dot {peer.status}"></span>
                        <div class="peer-main">
                            <div class="peer-name">{peer.name}</div>
                            <div class="peer-addr">{peer.addr}</div>
                        </div>
                        <div class="peer-meta">{peer.meta}</div>
                    </div>
                {/each}
            </div>
        {/if}
        <p class="stub-note">
            Live QUIC PeerBook data (latency, missed pings, TOFU pins) isn't
            exposed over the node API yet — this list shows account
            reachability instead.
        </p>
    </div>

    <div class="settings-section">
        <h3>Bootstrap peers</h3>
        <div class="settings-row-desc" style="margin-bottom:4px;">Add a known peer address to help your node find the rest of the network.</div>
        <div class="add-row">
            <input
                type="text"
                bind:value={bootstrapInput}
                placeholder="node1… or host:port"
                onkeydown={(e) => e.key === "Enter" && addBootstrap()}
            />
            <button class="settings-btn" onclick={addBootstrap}>Add</button>
        </div>
    </div>
</div>

<style>
    :global {
        .settings-panel {
            flex-grow: 1;
            display: none;
            flex-direction: column;
            background: var(--cream);
            padding: 32px 44px;
            overflow-y: auto;
            min-width: 0;
        }

        .settings-panel.active {
            display: flex;
        }

        .settings-panel .settings-title {
            font-family: var(--ui);
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 6px;
        }

        .settings-panel .settings-sub {
            font-size: 0.82rem;
            color: var(--ink-faint);
            margin-bottom: 34px;
        }

        .settings-panel .settings-section {
            max-width: 560px;
            margin-bottom: 34px;
            padding-bottom: 34px;
            border-bottom: 1px solid var(--glass-border);
        }

        .settings-panel .settings-section:last-of-type {
            border-bottom: none;
        }

        .settings-panel .settings-section h3 {
            font-family: var(--ui);
            font-size: 0.68rem;
            font-weight: 600;
            color: var(--ink-faint);
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 16px;
        }

        .settings-panel .settings-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            padding: 12px 0;
        }

        .settings-panel .settings-row-label {
            font-size: 0.86rem;
            color: var(--ink);
            font-weight: 500;
        }

        .settings-panel .settings-row-desc {
            font-size: 0.74rem;
            color: var(--ink-faint);
            margin-top: 2px;
        }

        .settings-panel .settings-node-id {
            font-family: var(--ui);
            font-size: 0.78rem;
            color: var(--ink-dim);
            background: var(--glass-strong);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius-sm);
            padding: 11px 14px;
            word-break: break-all;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
        }

        .settings-panel .settings-node-id button {
            color: var(--ink-faint);
            flex-shrink: 0;
        }

        .settings-panel .settings-node-id button:hover {
            color: var(--accent);
        }

        .settings-panel .settings-node-id button svg {
            width: 15px;
            height: 15px;
            stroke: currentColor;
            fill: none;
            stroke-width: 1.9;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        .settings-panel .tag {
            background: var(--glass-strong);
            border: 1px solid var(--glass-border);
            color: var(--ink-dim);
            padding: 6px 12px;
            border-radius: var(--radius-sm);
            font-size: 0.72rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 7px;
            font-family: var(--ui);
        }

        .settings-panel .stat-row {
            display: flex;
            gap: 28px;
            flex-wrap: wrap;
            margin-bottom: 6px;
        }

        .settings-panel .stat {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }

        .settings-panel .stat .stat-num {
            font-family: var(--ui);
            font-size: 1.5rem;
            font-weight: 600;
            color: var(--ink);
        }

        .settings-panel .stat .stat-label {
            font-size: 0.68rem;
            color: var(--ink-faint);
        }

        .settings-panel .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            flex-shrink: 0;
        }

        .settings-panel .status-dot.up { background: var(--direct); }
        .settings-panel .status-dot.degraded { background: var(--relay); }
        .settings-panel .status-dot.down { background: var(--ink-faint); }

        .settings-panel .peer-row {
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 12px 0;
            border-bottom: 1px solid var(--glass-border);
        }

        .settings-panel .peer-row:last-child {
            border-bottom: none;
        }

        .settings-panel .peer-main {
            flex: 1;
            min-width: 0;
        }

        .settings-panel .peer-name {
            font-size: 0.86rem;
            font-weight: 600;
            color: var(--ink);
        }

        .settings-panel .peer-addr {
            font-size: 0.72rem;
            color: var(--ink-faint);
            font-family: var(--ui);
            word-break: break-all;
        }

        .settings-panel .peer-meta {
            font-size: 0.7rem;
            color: var(--ink-faint);
            white-space: nowrap;
            text-align: right;
        }

        .settings-panel .empty-note {
            padding: 24px 0;
            color: var(--ink-faint);
            font-size: 0.82rem;
        }

        .settings-panel .stub-note {
            font-size: 0.7rem;
            color: var(--ink-faint);
            margin-top: 10px;
            max-width: 52ch;
        }

        .settings-panel .add-row {
            display: flex;
            gap: 10px;
            margin-top: 16px;
        }

        .settings-panel .add-row input {
            flex: 1;
            background: var(--glass-strong);
            border: 1px solid var(--glass-border);
            border-radius: 100px;
            padding: 9px 16px;
            font-size: 0.82rem;
            color: var(--ink);
            outline: none;
            font-family: var(--body);
        }

        .settings-panel .add-row input::placeholder {
            color: var(--ink-faint);
        }

        .settings-panel .settings-btn {
            font-family: var(--ui);
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--ink);
            background: var(--glass-strong);
            border: 1px solid var(--glass-border);
            padding: 9px 18px;
            border-radius: 100px;
            transition: background 0.15s ease, transform 0.15s ease;
        }

        .settings-panel .settings-btn:hover {
            background: var(--glass-solid);
            transform: translateY(-1px);
        }
    }
</style>
