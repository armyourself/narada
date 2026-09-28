"use client";

import type { ReactNode } from "react";

interface LandingProps {
    children: ReactNode;
}

export default function Landing({ children }: LandingProps) {
    return (
        <section className="flex items-center justify-center w-full h-full flex-col">
            <div className="text-center mb-8">
                <h1 className="text-2xl font-semibold text-notion-text mb-1">Narada</h1>
                <p className="text-sm text-notion-text-muted">
                    Decentralized email with end-to-end encryption
                </p>
            </div>
            <div className="w-[480px] bg-notion-surface border border-notion-border rounded-xl shadow-notion-float p-6">
                <section className="register-container">{children}</section>
            </div>
        </section>
    );
}
