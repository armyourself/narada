import { SharedStore } from "$lib/stores/shared.svelte";

export interface NaradaIdentity {
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

async function apiGet<T>(path: string): Promise<{ success: boolean; message: string; data?: T }> {
    const response = await fetch(SharedStore.server + path);
    return response.json();
}

async function apiPost<T>(path: string, body: unknown): Promise<{ success: boolean; message: string; data?: T }> {
    const response = await fetch(SharedStore.server + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    return response.json();
}

async function apiDelete(path: string): Promise<{ success: boolean; message: string }> {
    const response = await fetch(SharedStore.server + path, { method: "DELETE" });
    return response.json();
}

export class NaradaIdentityService {
    static async getIdentity(accountId: string): Promise<NaradaIdentity | null> {
        const result = await apiGet<NaradaIdentity>(
            `/Narada/identity/${encodeURIComponent(accountId)}`
        );
        if (result.success && result.data) return result.data;
        return null;
    }

    static async generateIdentity(accountId: string): Promise<GenerateIdentityResult | null> {
        const result = await apiPost<GenerateIdentityResult>(
            "/Narada/identity/generate",
            { account_id: accountId }
        );
        if (result.success && result.data) return result.data;
        return null;
    }

    static async claimMnemonic(accountId: string, token: string): Promise<MnemonicClaimResult | null> {
        const result = await apiGet<MnemonicClaimResult>(
            `/Narada/identity/${encodeURIComponent(accountId)}/mnemonic?token=${encodeURIComponent(token)}`
        );
        if (result.success && result.data) return result.data;
        return null;
    }

    static async recoverIdentity(
        accountId: string,
        mnemonic: string
    ): Promise<NaradaIdentity | null> {
        const result = await apiPost<NaradaIdentity>(
            "/Narada/identity/recover",
            { account_id: accountId, mnemonic }
        );
        if (result.success && result.data) return result.data;
        return null;
    }

    static async rotateIdentity(accountId: string): Promise<GenerateIdentityResult | null> {
        const result = await apiPost<GenerateIdentityResult>(
            "/Narada/identity/rotate",
            { account_id: accountId }
        );
        if (result.success && result.data) return result.data;
        return null;
    }

    static async rotateX25519(accountId: string): Promise<GenerateIdentityResult | null> {
        const result = await apiPost<GenerateIdentityResult>(
            "/Narada/identity/rotate-x25519",
            { account_id: accountId }
        );
        if (result.success && result.data) return result.data;
        return null;
    }

    static async deleteIdentity(accountId: string): Promise<boolean> {
        const result = await apiDelete(
            `/Narada/identity/${encodeURIComponent(accountId)}`
        );
        return result.success;
    }
}
