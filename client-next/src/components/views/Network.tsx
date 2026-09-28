"use client";

import { useEffect, useMemo, useState } from "react";
import { useSharedStore } from "@/lib/stores/shared";
import { useNostrIdentity } from "@/lib/nostr/identity";
import { showToast } from "@/lib/stores/ui";
import "./network.css";

interface RelayRow {
    url: string;
    connected: boolean;
    last_error: string | null;
}

interface PeerRow {
    status: "up" | "down";
    name: string;
    addr: string;
    meta: string;
}

export default function Network() {
    const [bootstrapInput, setBootstrapInput] = useState("");
    const [relays, setRelays] = useState<RelayRow[]>([]);
    const [isLoadingRelays, setIsLoadingRelays] = useState(false);

    const { npub, publicId } = useNostrIdentity();
    const accounts = useSharedStore((s) => s.accounts);
    const failedAccounts = useSharedStore((s) => s.failedAccounts);
    const server = useSharedStore((s) => s.server);

    const nodeId = useMemo(
        () => npub || publicId || "no identity on this account",
        [npub, publicId],
    );

    const peers = useMemo(() => {
        const rows: PeerRow[] = accounts.map((account) => ({
            status: "up",
            name: account.fullname || account.email_address,
            addr: account.email_address,
            meta: "server reachable",
        }));
        failedAccounts.forEach((account) => {
            rows.push({
                status: "down",
                name: account.fullname || account.email_address,
                addr: account.email_address,
                meta: "unreachable",
            });
        });
        return rows;
    }, [accounts, failedAccounts]);

    const downCount = useMemo(
        () => peers.filter((p) => p.status === "down").length,
        [peers],
    );
    const relaysConnected = useMemo(
        () => relays.filter((r) => r.connected).length,
        [relays],
    );

    useEffect(() => {
        let cancelled = false;
        const fetchRelays = async () => {
            setIsLoadingRelays(true);
            try {
                const res = await fetch(`${server}/nostr/relays`);
                const json = await res.json();
                if (cancelled) return;
                if (json.success && Array.isArray(json.data)) {
                    setRelays(json.data);
                }
            } catch {
                if (cancelled) return;
                setRelays([]);
            } finally {
                if (!cancelled) setIsLoadingRelays(false);
            }
        };
        fetchRelays();
        return () => {
            cancelled = true;
        };
    }, [server]);

    const copyNodeId = async () => {
        try {
            await navigator.clipboard.writeText(nodeId);
            showToast({ content: "node id copied" });
        } catch {
            /* clipboard unavailable — ignore */
        }
    };

    const addBootstrap = () => {
        const value = bootstrapInput.trim();
        if (!value) return;
        showToast({
            content: "bootstrap peers need the node API — not wired yet",
        });
        setBootstrapInput("");
    };

    const relayName = (url: string): string => {
        try {
            return new URL(url).hostname;
        } catch {
            return url;
        }
    };

    return (
        <div className="settings-panel active">
            <div className="settings-title">Node network</div>
            <div className="settings-sub">Who your node is talking to right now.</div>

            <div className="settings-section">
                <h3>Your node</h3>
                <div className="settings-node-id">
                    <span>{nodeId}</span>
                    <button onClick={copyNodeId} title="Copy" aria-label="Copy node id">
                        <svg viewBox="0 0 24 24"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                    </button>
                </div>
                <div className="settings-row">
                    <div>
                        <div className="settings-row-label">Status</div>
                        <div className="settings-row-desc">Connected to Nostr relays for decentralized mail delivery.</div>
                    </div>
                    <div className="tag">
                        <span className={"status-dot " + (relaysConnected > 0 ? "up" : "down")}></span>
                        {relaysConnected > 0 ? `${relaysConnected} relay${relaysConnected !== 1 ? "s" : ""}` : "offline"}
                    </div>
                </div>
            </div>

            <div className="settings-section">
                <h3>Network health</h3>
                <div className="stat-row">
                    <div className="stat"><span className="stat-num">{relays.length}</span><span className="stat-label">relays configured</span></div>
                    <div className="stat"><span className="stat-num">{relaysConnected}</span><span className="stat-label">connected</span></div>
                    <div className="stat"><span className="stat-num">{peers.length}</span><span className="stat-label">accounts</span></div>
                    <div className="stat"><span className="stat-num">{downCount}</span><span className="stat-label">failed</span></div>
                </div>
            </div>

            <div className="settings-section">
                <h3>Nostr relays</h3>
                {isLoadingRelays ? (
                    <div className="empty-note">Loading relay status…</div>
                ) : relays.length === 0 ? (
                    <div className="empty-note">No relays configured. Register a Nostr identity to connect.</div>
                ) : (
                    <div className="peer-list">
                        {relays.map((relay, index) => (
                            <div className="peer-row" key={`${relay.url}-${index}`}>
                                <span className={"status-dot " + (relay.connected ? "up" : "down")}></span>
                                <div className="peer-main">
                                    <div className="peer-name">{relayName(relay.url)}</div>
                                    <div className="peer-addr">{relay.url}</div>
                                </div>
                                <div className="peer-meta">
                                    {relay.connected
                                        ? "connected"
                                        : relay.last_error
                                            ? relay.last_error
                                            : "disconnected"}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <div className="settings-section">
                <h3>Connected accounts</h3>
                {peers.length === 0 ? (
                    <div className="empty-note">No accounts yet.</div>
                ) : (
                    <div className="peer-list">
                        {peers.map((peer, index) => (
                            <div className="peer-row" key={`${peer.addr}-${index}`}>
                                <span className={"status-dot " + (peer.status === "up" ? "up" : "down")}></span>
                                <div className="peer-main">
                                    <div className="peer-name">{peer.name}</div>
                                    <div className="peer-addr">{peer.addr}</div>
                                </div>
                                <div className="peer-meta">{peer.meta}</div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <div className="settings-section">
                <h3>Bootstrap peers</h3>
                <div className="settings-row-desc" style={{ marginBottom: "4px" }}>Add a known peer address to help your node find the rest of the network.</div>
                <div className="add-row">
                    <input
                        type="text"
                        value={bootstrapInput}
                        onChange={(e) => setBootstrapInput(e.target.value)}
                        placeholder="node1… or host:port"
                        onKeyDown={(e) => {
                            if (e.key === "Enter") addBootstrap();
                        }}
                    />
                    <button className="settings-btn" onClick={addBootstrap}>Add</button>
                </div>
            </div>
        </div>
    );
}
