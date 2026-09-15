export type MainView = "inbox" | "network" | "contacts" | "settings";
export type DeliveryRoute = "direct" | "relay" | "gateway";

interface MainNavState {
    view: MainView;
    folder: string;
    routeFilter: DeliveryRoute | null;
}

export let MainNav: MainNavState = $state({
    view: "inbox",
    folder: "inbox",
    routeFilter: null,
});

export function showView(view: MainView): void {
    MainNav.view = view;
}

export function selectFolder(folder: string): void {
    MainNav.folder = folder;
    MainNav.view = "inbox";
}

export function toggleRouteFilter(route: DeliveryRoute): void {
    MainNav.routeFilter = MainNav.routeFilter === route ? null : route;
}
