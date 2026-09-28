"use client";

export default function ViewPlaceholder({ title }: { title: string }) {
    return (
        <div className="flex-1 flex flex-col h-full overflow-hidden">
            <header className="h-[50px] border-b border-notion-border px-6 flex items-center flex-shrink-0 bg-notion-canvas">
                <h1 className="text-base font-semibold text-notion-text">{title}</h1>
            </header>
            <div className="flex-1 flex items-center justify-center text-notion-text-muted text-sm">
                {title} view is being ported to Next.js.
            </div>
        </div>
    );
}
