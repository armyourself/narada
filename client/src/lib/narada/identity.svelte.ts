import { NaradaIdentityService } from "$lib/services/NaradaIdentityService";
import { SharedStore } from "$lib/stores/shared.svelte";

export interface NaradaIdentityState {
    accountId: string;
    publicId: string | null;
    loading: boolean;
    error: string | null;
}

export class NaradaIdentityManager {
    private _state: NaradaIdentityState = $state({
        accountId: "",
        publicId: null,
        loading: false,
        error: null,
    });

    get state(): NaradaIdentityState {
        return this._state;
    }

    get hasIdentity(): boolean {
        return this._state.publicId !== null;
    }

    async loadIdentity(accountId: string): Promise<boolean> {
        this._state.accountId = accountId;
        this._state.loading = true;
        this._state.error = null;

        try {
            const identity = await NaradaIdentityService.getIdentity(accountId);
            if (identity) {
                this._state.publicId = identity.public_id;
                this._state.loading = false;
                return true;
            }
            this._state.publicId = null;
            this._state.loading = false;
            return false;
        } catch (err) {
            this._state.error = err instanceof Error ? err.message : "Failed to load identity";
            this._state.loading = false;
            return false;
        }
    }

    async generateIdentity(accountId: string): Promise<{ publicId: string; mnemonicToken: string } | null> {
        this._state.accountId = accountId;
        this._state.loading = true;
        this._state.error = null;

        try {
            const result = await NaradaIdentityService.generateIdentity(accountId);
            if (result) {
                this._state.publicId = result.public_id;
                this._state.loading = false;
                return { publicId: result.public_id, mnemonicToken: result.mnemonic_claim_token };
            }
            this._state.loading = false;
            return null;
        } catch (err) {
            this._state.error = err instanceof Error ? err.message : "Failed to generate identity";
            this._state.loading = false;
            return null;
        }
    }

    async recoverIdentity(accountId: string, mnemonic: string): Promise<string | null> {
        this._state.accountId = accountId;
        this._state.loading = true;
        this._state.error = null;

        try {
            const identity = await NaradaIdentityService.recoverIdentity(accountId, mnemonic);
            if (identity) {
                this._state.publicId = identity.public_id;
                this._state.loading = false;
                return identity.public_id;
            }
            this._state.loading = false;
            return null;
        } catch (err) {
            this._state.error = err instanceof Error ? err.message : "Failed to recover identity";
            this._state.loading = false;
            return null;
        }
    }

    async deleteIdentity(accountId: string): Promise<boolean> {
        this._state.loading = true;
        this._state.error = null;

        try {
            const success = await NaradaIdentityService.deleteIdentity(accountId);
            if (success) {
                this._state.publicId = null;
                this._state.accountId = "";
            }
            this._state.loading = false;
            return success;
        } catch (err) {
            this._state.error = err instanceof Error ? err.message : "Failed to delete identity";
            this._state.loading = false;
            return false;
        }
    }
}

export const naradaIdentity = new NaradaIdentityManager();
