import { create } from "zustand";
import { NostrIdentityService } from "@/lib/services/NostrIdentityService";

export interface NostrIdentityState {
    accountId: string;
    publicId: string | null;
    npub: string | null;
    loading: boolean;
    error: string | null;
}

interface NostrIdentityActions {
    loadIdentity: (accountId: string) => Promise<boolean>;
    generateIdentity: (
        accountId: string,
    ) => Promise<{ publicId: string; npub: string; mnemonicToken: string } | null>;
    recoverIdentity: (accountId: string, mnemonic: string) => Promise<string | null>;
    deleteIdentity: (accountId: string) => Promise<boolean>;
    clear: () => void;
}

const initialState: NostrIdentityState = {
    accountId: "",
    publicId: null,
    npub: null,
    loading: false,
    error: null,
};

export const useNostrIdentity = create<NostrIdentityState & NostrIdentityActions>(
    (set) => ({
        ...initialState,

        async loadIdentity(accountId) {
            set({ accountId, loading: true, error: null });
            try {
                const identity = await NostrIdentityService.getIdentity(accountId);
                if (identity) {
                    set({ publicId: identity.public_id, npub: identity.npub, loading: false });
                    return true;
                }
                set({ publicId: null, npub: null, loading: false });
                return false;
            } catch (err) {
                set({
                    error: err instanceof Error ? err.message : "Failed to load identity",
                    loading: false,
                });
                return false;
            }
        },

        async generateIdentity(accountId) {
            set({ accountId, loading: true, error: null });
            try {
                const result = await NostrIdentityService.generateIdentity(accountId);
                if (result) {
                    set({
                        publicId: result.public_id,
                        npub: result.npub,
                        loading: false,
                    });
                    return {
                        publicId: result.public_id,
                        npub: result.npub,
                        mnemonicToken: result.mnemonic_claim_token,
                    };
                }
                set({ loading: false });
                return null;
            } catch (err) {
                set({
                    error: err instanceof Error ? err.message : "Failed to generate identity",
                    loading: false,
                });
                return null;
            }
        },

        async recoverIdentity(accountId, mnemonic) {
            set({ accountId, loading: true, error: null });
            try {
                const identity = await NostrIdentityService.recoverIdentity(accountId, mnemonic);
                if (identity) {
                    set({
                        publicId: identity.public_id,
                        npub: identity.npub,
                        loading: false,
                    });
                    return identity.public_id;
                }
                set({ loading: false });
                return null;
            } catch (err) {
                set({
                    error: err instanceof Error ? err.message : "Failed to recover identity",
                    loading: false,
                });
                return null;
            }
        },

        async deleteIdentity(accountId) {
            set({ loading: true, error: null });
            try {
                const success = await NostrIdentityService.deleteIdentity(accountId);
                if (success) {
                    set({ publicId: null, npub: null, accountId: "" });
                }
                set({ loading: false });
                return success;
            } catch (err) {
                set({
                    error: err instanceof Error ? err.message : "Failed to delete identity",
                    loading: false,
                });
                return false;
            }
        },

        clear() {
            set(initialState);
        },
    }),
);

export const nostrIdentity = {
    get state(): NostrIdentityState {
        return useNostrIdentity.getState();
    },
    get hasIdentity(): boolean {
        return useNostrIdentity.getState().publicId !== null;
    },
    loadIdentity: (accountId: string) => useNostrIdentity.getState().loadIdentity(accountId),
    generateIdentity: (accountId: string) => useNostrIdentity.getState().generateIdentity(accountId),
    recoverIdentity: (accountId: string, mnemonic: string) =>
        useNostrIdentity.getState().recoverIdentity(accountId, mnemonic),
    deleteIdentity: (accountId: string) => useNostrIdentity.getState().deleteIdentity(accountId),
    clear: () => useNostrIdentity.getState().clear(),
};
