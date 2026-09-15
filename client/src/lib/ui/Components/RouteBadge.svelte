<script lang="ts" module>
    import type { DeliveryRoute } from "$lib/stores/mainNav.svelte";

    export const routeMeta: Record<DeliveryRoute, { label: string; icon: string }> = {
        direct: { label: "Direct", icon: '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>' },
        relay: { label: "Via relay", icon: '<path d="M3 7h4l4 5h6"/><path d="M3 17h4l4-5"/><path d="m17 5 4 2-4 2"/><path d="m17 15 4 2-4 2"/>' },
        gateway: { label: "Via gateway", icon: '<path d="M8 7h8"/><path d="M8 17h8"/><path d="M16 7l4 5-4 5"/><path d="M8 7l-4 5 4 5"/>' },
    };

    /**
     * Infer the delivery route of an email from its sender address.
     *
     * The IMAP-era mailbox model carries no transport metadata, so we
     * use the only observable signal: native Narada senders appear as
     * bech32m ids ("narada1…" / "node1…"), while anything with a
     * conventional @domain address arrived through the SMTP gateway.
     * Relay-delivered native mail is indistinguishable from direct at
     * this layer and is reported as direct until the protocol exposes
     * route metadata (Phase 6 formalization).
     */
    export function emailRoute(email: { sender?: string }): DeliveryRoute {
        const sender = email.sender ?? "";
        const isNaradaId = /(?:^|<\s*)[a-z0-9]{1,8}1[a-z0-9]{20,}/i.test(sender);
        return isNaradaId ? "direct" : "gateway";
    }
</script>

<script lang="ts">
    let { route, hollow = false }: { route: DeliveryRoute; hollow?: boolean } = $props();
</script>

<span class="rbadge {route}" class:hollow>
    <svg viewBox="0 0 24 24">{@html routeMeta[route].icon}</svg>
    {routeMeta[route].label}
</span>

<style>
    :global {
        .rbadge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-family: var(--ui);
            font-size: 0.58rem;
            font-weight: 600;
            padding: 1px 7px;
            border-radius: 100px;
            border: 1px solid;
            white-space: nowrap;
        }
        .rbadge svg {
            width: 10px;
            height: 10px;
            stroke: currentColor;
            fill: none;
            stroke-width: 2.2;
            stroke-linecap: round;
            stroke-linejoin: round;
            flex-shrink: 0;
        }
        .rbadge.direct {
            color: var(--direct);
            border-color: color-mix(in srgb, var(--direct) 40%, transparent);
            background: color-mix(in srgb, var(--direct) 10%, transparent);
        }
        .rbadge.relay {
            color: var(--relay);
            border-style: dashed;
            border-color: color-mix(in srgb, var(--relay) 45%, transparent);
            background: color-mix(in srgb, var(--relay) 9%, transparent);
        }
        .rbadge.gateway {
            color: var(--gateway);
            border-radius: 5px;
            border-color: color-mix(in srgb, var(--gateway) 40%, transparent);
            background: color-mix(in srgb, var(--gateway) 9%, transparent);
        }
        /* hollow variant: used inside the reading pane tag row where the
           solid pill backgrounds read too heavy against --cream */
        .rbadge.hollow {
            background: transparent;
        }
    }
</style>
