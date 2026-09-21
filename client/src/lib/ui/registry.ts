/**
 * Component registry -- maps logical component names to implementations.
 * Updated to match the Notion Mail frontend.html design.
 */

import Main from "./Layout/Main.svelte";
import Landing from "./Layout/Landing.svelte";
import Loading from "./Layout/Loading.svelte";

import Network from "./Layout/Main/Views/Network.svelte";
import Contacts from "./Layout/Main/Views/Contacts.svelte";
import Settings from "./Layout/Main/Views/Settings.svelte";

import Content from "./Layout/Main/Content.svelte";

export const registry = {
    layout: {
        main: Main,
        landing: Landing,
        loading: Loading,
    },

    dashboard: {
        content: Content,
    },

    views: {
        network: Network,
        contacts: Contacts,
        settings: Settings,
    },
} as const;

export type Registry = typeof registry;
