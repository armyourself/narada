import { create } from "zustand";
import type { Email } from "@/lib/types";

export type MainView = "inbox" | "network" | "contacts" | "settings";
export type DeliveryRoute = "direct" | "relay" | "gateway";

interface MainNavState {
    view: MainView;
    folder: string;
    routeFilter: DeliveryRoute | null;
    searchQuery: string;
    // The open reading-pane message. Lives in the store so any surface
    // (list rows, search palette) can open it without effect plumbing.
    selectedEmail: Email | null;
    showView: (view: MainView) => void;
    selectFolder: (folder: string) => void;
    toggleRouteFilter: (route: DeliveryRoute) => void;
    setSearchQuery: (query: string) => void;
    selectEmail: (email: Email | null) => void;
}

export const useMainNav = create<MainNavState>((set) => ({
    view: "inbox",
    folder: "Inbox",
    routeFilter: null,
    searchQuery: "",
    selectedEmail: null,
    showView: (view) => set({ view }),
    selectFolder: (folder) => set({ folder, view: "inbox" }),
    toggleRouteFilter: (route) =>
        set((state) => ({ routeFilter: state.routeFilter === route ? null : route })),
    setSearchQuery: (query) => set({ searchQuery: query }),
    selectEmail: (email) => set({ selectedEmail: email }),
}));
