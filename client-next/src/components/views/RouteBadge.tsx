"use client";

import type { DeliveryRoute } from "@/lib/stores/mainNav";
import "./RouteBadge.css";

export const routeMeta: Record<DeliveryRoute, { label: string; icon: string }> = {
    direct: { label: "Direct", icon: '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>' },
    relay: { label: "Via relay", icon: '<path d="M3 7h4l4 5h6"/><path d="M3 17h4l4-5"/><path d="m17 5 4 2-4 2"/><path d="m17 15 4 2-4 2"/>' },
    gateway: { label: "Via gateway", icon: '<path d="M8 7h8"/><path d="M8 17h8"/><path d="M16 7l4 5-4 5"/><path d="M8 7l-4 5 4 5"/>' },
};

/**
 * Infer the delivery route of an email from its sender address.
 *
 * The IMAP-era mailbox model carries no transport metadata, so we
 * use the only observable signal: native Nostr senders appear as
 * bech32m ids ("npub1…" / "nsec1…"), while anything with a
 * conventional @domain address arrived through the SMTP gateway.
 * Relay-delivered native mail is indistinguishable from direct at
 * this layer and is reported as direct until the protocol exposes
 * route metadata (Phase 6 formalization).
 */
export function emailRoute(email: { sender?: string }): DeliveryRoute {
    const sender = email.sender ?? "";
    const isNostrId = /(?:^|<\s*)[a-z0-9]{1,8}1[a-z0-9]{20,}/i.test(sender);
    return isNostrId ? "direct" : "gateway";
}

/**
 * Delivery route for a mailbox email.
 *
 * Prefers the backend-reported route (authoritative: the server knows
 * which transport served the message).  Falls back to the sender
 * heuristic only for rows that predate route metadata; in that case a
 * Nostr-sourced message from a conventional address is reported as
 * relay, since it cannot be direct.
 */
export function emailDeliveryRoute(email: {
    sender?: string;
    route?: DeliveryRoute;
    source?: string;
}): DeliveryRoute {
    if (email.route === "direct" || email.route === "relay" || email.route === "gateway") {
        return email.route;
    }
    if (email.source === "nostr") {
        return emailRoute(email) === "direct" ? "direct" : "relay";
    }
    return emailRoute(email);
}

export default function RouteBadge({ route, hollow = false }: { route: DeliveryRoute; hollow?: boolean }) {
    return (
        <span className={hollow ? `rbadge ${route} hollow` : `rbadge ${route}`}>
            <svg viewBox="0 0 24 24" dangerouslySetInnerHTML={{ __html: routeMeta[route].icon }} />
            {routeMeta[route].label}
        </span>
    );
}
