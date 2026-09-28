import { create } from "zustand";
import type {
    Email,
    Account,
    Mailbox,
    OpenmailTaskResults,
} from "@/lib/types";

export enum SharedStoreKeys {
    server = "server",
    isAppLoaded = "isAppLoaded",
    accounts = "accounts",
    currentAccount = "currentAccount",
    folders = "folders",
    hierarchyDelimiters = "hierarchyDelimiters",
    recentEmailsChannel = "recentEmailsChannel",
    mailboxes = "mailboxes",
    failedAccounts = "failedAccounts",
    accountsWithFailedFolders = "accountsWithFailedFolders",
    accountsWithFailedMailboxes = "accountsWithFailedMailboxes",
}

interface ISharedStore {
    [SharedStoreKeys.server]: string;
    [SharedStoreKeys.isAppLoaded]: boolean;
    [SharedStoreKeys.accounts]: Account[];
    [SharedStoreKeys.currentAccount]: "home" | Account;
    [SharedStoreKeys.folders]: OpenmailTaskResults<{
        standard: string[],
        custom: string[]
    }>;
    [SharedStoreKeys.hierarchyDelimiters]: OpenmailTaskResults<string>;
    [SharedStoreKeys.recentEmailsChannel]: OpenmailTaskResults<Email[]>;
    [SharedStoreKeys.mailboxes]: OpenmailTaskResults<Mailbox>;
    [SharedStoreKeys.failedAccounts]: Account[];
    [SharedStoreKeys.accountsWithFailedFolders]: Account[];
    [SharedStoreKeys.accountsWithFailedMailboxes]: Account[];
}

export type SharedState = { [K in SharedStoreKeys]: ISharedStore[K] };

export const useSharedStore = create<SharedState>(() => ({
    [SharedStoreKeys.server]: "",
    [SharedStoreKeys.isAppLoaded]: false,
    [SharedStoreKeys.accounts]: [],
    [SharedStoreKeys.currentAccount]: "home",
    [SharedStoreKeys.folders]: {},
    [SharedStoreKeys.hierarchyDelimiters]: {},
    [SharedStoreKeys.recentEmailsChannel]: {},
    [SharedStoreKeys.mailboxes]: {},
    [SharedStoreKeys.failedAccounts]: [],
    [SharedStoreKeys.accountsWithFailedFolders]: [],
    [SharedStoreKeys.accountsWithFailedMailboxes]: [],
}));

export const SharedStore = new Proxy({} as SharedState, {
    get: (_target, prop) => (useSharedStore.getState() as Record<PropertyKey, unknown>)[prop],
    set: (_target, prop, value) => {
        useSharedStore.setState({ [prop]: value } as Partial<SharedState>);
        return true;
    },
    has: (_target, prop) => Object.hasOwn(useSharedStore.getState(), prop),
    ownKeys: () => Reflect.ownKeys(useSharedStore.getState()),
    getOwnPropertyDescriptor: (_target, prop) => ({
        enumerable: true,
        configurable: true,
        value: (useSharedStore.getState() as Record<PropertyKey, unknown>)[prop],
    }),
});
