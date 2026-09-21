import { SharedStore } from "$lib/stores/shared.svelte";

export interface NostrIdentity {
    account_id: string;
    public_id: string;
}

export interface GenerateIdentityResult {
    account_id: string;
    public_id: string;
    mnemonic_claim_token: string;
}

export interface MnemonicClaimResult {
    account_id: string;
    public_id: string;
    mnemonic: string;
}

const STORAGE_PREFIX = "openmail_nostr_";

function storeKey(accountId: string) {
    return STORAGE_PREFIX + accountId;
}

function generateNpub(pubkey: string): string {
    // Simple bech32 encoding for npub prefix
    return "npub1" + pubkey.slice(0, 12) + "…";
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

        // Generate a random 32-byte hex pubkey
        const bytes = new Uint8Array(32);
        crypto.getRandomValues(bytes);
        const pubkey = Array.from(bytes).map(b => b.toString(16).padStart(2, "0")).join("");

        const identity: NostrIdentity = {
            account_id: accountId,
            public_id: pubkey,
        };

        localStorage.setItem(storeKey(accountId), JSON.stringify(identity));

        const mnemonicToken = crypto.randomUUID();
        localStorage.setItem(storeKey(accountId) + "_mnemonic_" + mnemonicToken, generateMnemonic());

        return {
            account_id: accountId,
            public_id: pubkey,
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
            mnemonic,
        };
    }

    static async recoverIdentity(
        accountId: string,
        mnemonic: string
    ): Promise<NostrIdentity | null> {
        // Derive a deterministic pubkey from the mnemonic
        const encoder = new TextEncoder();
        const data = encoder.encode(mnemonic);
        const hashBuffer = await crypto.subtle.digest("SHA-256", data);
        const pubkey = Array.from(new Uint8Array(hashBuffer))
            .map(b => b.toString(16).padStart(2, "0"))
            .join("");

        const identity: NostrIdentity = {
            account_id: accountId,
            public_id: pubkey,
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
