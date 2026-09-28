"use client";

import type { ReactNode } from "react";
import Sidebar from "./Sidebar";

interface MainProps {
    children: ReactNode;
}

export default function Main({ children }: MainProps) {
    return (
        <div className="flex h-full w-full bg-notion-canvas">
            <div className="flex-shrink-0 h-full">
                <Sidebar />
            </div>
            <main className="flex-1 flex flex-col h-full bg-notion-canvas overflow-hidden relative">
                {children}
            </main>
        </div>
    );
}
