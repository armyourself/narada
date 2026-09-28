"use client";

import Shell from "@/components/layout/Shell";
import LandingFlow from "@/components/layout/LandingFlow";
import Main from "@/components/layout/Main";
import Content from "@/components/layout/Content";
import Network from "@/components/views/Network";
import Contacts from "@/components/views/Contacts";
import Settings from "@/components/views/Settings";
import { useSharedStore } from "@/lib/stores/shared";
import { useMainNav, type MainView } from "@/lib/stores/mainNav";
import { getCurrentMailbox } from "@/lib/mailbox/getCurrentMailbox";
import { useEffect } from "react";

const DEV_VIEWS: MainView[] = ["network", "contacts", "settings"];

function Dashboard() {
    const mailboxes = useSharedStore((s) => s.mailboxes);
    const currentAccount = useSharedStore((s) => s.currentAccount);
    const view = useMainNav((s) => s.view);

    useEffect(() => {
        if (process.env.NODE_ENV !== "development") return;
        const requested = new URLSearchParams(window.location.search).get("view");
        if (DEV_VIEWS.includes(requested as MainView)) {
            useMainNav.getState().showView(requested as MainView);
        }
    }, []);

    const isMailboxInitialized =
        Object.keys(mailboxes).length > 0 &&
        !!getCurrentMailbox({ mailboxes, currentAccount });

    if (!isMailboxInitialized) return <LandingFlow />;

    if (view === "network")
        return (
            <Main>
                <Network />
            </Main>
        );
    if (view === "contacts")
        return (
            <Main>
                <Contacts />
            </Main>
        );
    if (view === "settings")
        return (
            <Main>
                <Settings />
            </Main>
        );

    return (
        <Main>
            <Content />
        </Main>
    );
}

export default function Page() {
    return (
        <Shell>
            <Dashboard />
        </Shell>
    );
}
