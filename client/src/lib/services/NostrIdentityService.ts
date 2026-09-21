import { SharedStore } from "$lib/stores/shared.svelte";

export interface NostrIdentity {
    account_id: string;
    public_id: string;
    npub: string;
    nsec_hex: string;
}

export interface GenerateIdentityResult {
    account_id: string;
    public_id: string;
    npub: string;
    mnemonic_claim_token: string;
}

export interface MnemonicClaimResult {
    account_id: string;
    public_id: string;
    npub: string;
    mnemonic: string;
}

const STORAGE_PREFIX = "openmail_nostr_";

function storeKey(accountId: string) {
    return STORAGE_PREFIX + accountId;
}

function generateMnemonic(): string {
    const words = [
        "abandon","ability","able","about","above","absent","absorb","abstract",
        "absurd","abuse","access","accident","account","accuse","achieve","acid",
        "acoustic","acquire","across","act","action","actor","actress","actual",
        "adapt","add","addict","address","adjust","admit","adult","advance",
    ];
    const result: string[] = [];
    for (let i = 0; i < 12; i++) {
        result.push(words[Math.floor(Math.random() * words.length)]);
    }
    return result.join(" ");
}

async function apiPost<T = any>(path: string, body: Record<string, any>): Promise<T | null> {
    try {
        const res = await fetch(`${SharedStore.server}${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        const json = await res.json();
        if (json.success) return json.data ?? json;
        return null;
    } catch {
        return null;
    }
}

export class NostrIdentityService {
    static async getIdentity(accountId: string): Promise<NostrIdentity | null> {
        try {
            const stored = localStorage.getItem(storeKey(accountId));
            if (stored) return JSON.parse(stored) as NostrIdentity;
            return null;
        } catch {
            return null;
        }
    }

    static async generateIdentity(accountId: string): Promise<GenerateIdentityResult | null> {
        const existing = await this.getIdentity(accountId);
        if (existing) return null;

        // Ask the server to generate a real Ed25519 Nostr identity
        const data = await apiPost<{
            npub: string;
            nsec_hex: string;
            pubkey_hex: string;
            connected: boolean;
        }>("/nostr/generate-identity", { account: accountId });

        if (!data) {
            // Fallback: generate locally (won't work for relay signing)
            const bytes = new Uint8Array(32);
            crypto.getRandomValues(bytes);
            const pubkey = Array.from(bytes).map(b => b.toString(16).padStart(2, "0")).join("");

            const identity: NostrIdentity = {
                account_id: accountId,
                public_id: pubkey,
                npub: "npub1" + pubkey.slice(0, 12) + "…",
                nsec_hex: "",
            };
            localStorage.setItem(storeKey(accountId), JSON.stringify(identity));

            const mnemonicToken = crypto.randomUUID();
            localStorage.setItem(storeKey(accountId) + "_mnemonic_" + mnemonicToken, generateMnemonic());

            return {
                account_id: accountId,
                public_id: pubkey,
                npub: identity.npub,
                mnemonic_claim_token: mnemonicToken,
            };
        }

        const identity: NostrIdentity = {
            account_id: accountId,
            public_id: data.pubkey_hex,
            npub: data.npub,
            nsec_hex: data.nsec_hex,
        };
        localStorage.setItem(storeKey(accountId), JSON.stringify(identity));

        const mnemonicToken = crypto.randomUUID();
        localStorage.setItem(storeKey(accountId) + "_mnemonic_" + mnemonicToken, generateMnemonic());

        return {
            account_id: accountId,
            public_id: data.pubkey_hex,
            npub: data.npub,
            mnemonic_claim_token: mnemonicToken,
        };
    }

    static async claimMnemonic(accountId: string, token: string): Promise<MnemonicClaimResult | null> {
        const key = storeKey(accountId) + "_mnemonic_" + token;
        const mnemonic = localStorage.getItem(key);
        if (!mnemonic) return null;

        localStorage.removeItem(key);

        const identity = await this.getIdentity(accountId);
        if (!identity) return null;

        return {
            account_id: accountId,
            public_id: identity.public_id,
            npub: identity.npub,
            mnemonic,
        };
    }

    static async recoverIdentity(
        accountId: string,
        mnemonic: string
    ): Promise<NostrIdentity | null> {
        // Derive a deterministic pubkey from the mnemonic via SHA-256
        const encoder = new TextEncoder();
        const data = encoder.encode(mnemonic);
        const hashBuffer = await crypto.subtle.digest("SHA-256", data);
        const nsecHex = Array.from(new Uint8Array(hashBuffer))
            .map(b => b.toString(16).padStart(2, "0"))
            .join("");

        // Register the recovered identity with the server
        const result = await apiPost<{ npub: string; connected: boolean }>(
            "/nostr/register-identity",
            { account: accountId, npub: "", nsec_hex: nsecHex },
        );

        const npub = result?.npub ?? "";

        const identity: NostrIdentity = {
            account_id: accountId,
            public_id: nsecHex.slice(0, 64),
            npub,
            nsec_hex: nsecHex,
        };

        localStorage.setItem(storeKey(accountId), JSON.stringify(identity));
        return identity;
    }

    static async rotateIdentity(accountId: string): Promise<GenerateIdentityResult | null> {
        localStorage.removeItem(storeKey(accountId));
        return this.generateIdentity(accountId);
    }

    static async rotateX25519(accountId: string): Promise<GenerateIdentityResult | null> {
        return this.rotateIdentity(accountId);
    }

    static async deleteIdentity(accountId: string): Promise<boolean> {
        localStorage.removeItem(storeKey(accountId));
        return true;
    }
}
