/**
 * Component registry — maps logical component names to implementations.
 *
 * When the frontend.html design changes, update the imports here.
 * Components import from this registry instead of directly from file paths.
 *
 * Usage:
 *   import { registry } from "$lib/ui/registry";
 *   const Rail = registry.layout.rail;
 */

import Rail from "./Layout/Main/Rail.svelte";
import Menu from "./Layout/Main/Menu.svelte";
import Content from "./Layout/Main/Content.svelte";
import Main from "./Layout/Main.svelte";
import Titlebar from "./Layout/Titlebar.svelte";
import Background from "./Layout/Background.svelte";
import Landing from "./Layout/Landing.svelte";
import Loading from "./Layout/Loading.svelte";

import Network from "./Layout/Main/Views/Network.svelte";
import Contacts from "./Layout/Main/Views/Contacts.svelte";
import Settings from "./Layout/Main/Views/Settings.svelte";

import Compose from "./Layout/Main/Content/Compose.svelte";
import Mailbox from "./Layout/Main/Content/Mailbox.svelte";

export const registry = {
    /** Top-level layout shells. */
    layout: {
        main: Main,
        landing: Landing,
        titlebar: Titlebar,
        background: Background,
        loading: Loading,
    },

    /** Dashboard sub-layout components. */
    dashboard: {
        rail: Rail,
        menu: Menu,
        content: Content,
    },

    /** Full-page views (shown in the content area). */
    views: {
        network: Network,
        contacts: Contacts,
        settings: Settings,
    },

    /** Content panel components. */
    content: {
        compose: Compose,
        mailbox: Mailbox,
    },
} as const;

export type Registry = typeof registry;
