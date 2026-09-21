<script lang="ts">
    import type { Email } from "$lib/types";

    interface Props {
        email: Email;
        onClose: () => void;
    }

    let { email, onClose }: Props = $props();

    let replyText = $state("");

    function getSenderName(e: Email): string {
        const sender = e.sender || "";
        const match = sender.match(/"?([^"<]+)"?\s*</);
        return match ? match[1].trim() : sender.split("@")[0] || "Unknown";
    }

    function getSenderEmail(e: Email): string {
        const sender = e.sender || "";
        const match = sender.match(/<([^>]+)>/);
        return match ? match[1] : sender;
    }

    function handleKeydown(e: KeyboardEvent) {
        if (e.key === "Escape") onClose();
    }

    async function sendReply() {
        if (!replyText.trim()) return;
        replyText = "";
    }
</script>

<svelte:window on:keydown={handleKeydown} />

<!-- Thread Pane -->
<div class="absolute right-0 top-0 h-full w-full md:w-[620px] lg:w-[700px] bg-white dark:bg-[#181818] border-l border-notion-border dark:border-notion-border-dark shadow-2xl z-30 flex flex-col transition-all duration-300">
    <!-- Thread Header -->
    <div class="h-14 border-b border-notion-border dark:border-notion-border-dark px-6 flex items-center justify-between flex-shrink-0 bg-white/90 dark:bg-[#181818]/90 backdrop-blur">
        <div class="flex items-center space-x-2">
            <button class="p-1.5 hover:bg-notion-hover dark:hover:bg-notion-hover-dark rounded-md text-notion-text-muted hover:text-gray-800 dark:hover:text-gray-200 transition-colors" title="Close (Esc)" onclick={onClose}>
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
            <span class="text-xs text-notion-text-muted font-mono">Press Esc to close</span>
        </div>
        <div class="flex items-center space-x-1">
            <button class="p-1.5 hover:bg-notion-hover dark:hover:bg-notion-hover-dark rounded-md text-notion-text-muted transition-colors" title="Mark as Unread">
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.2 8.4c.5.38.8.97.8 1.6v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V10a2 2 0 0 1 .8-1.6l8-6a2 2 0 0 1 2.4 0l8 6Z"/><path d="m22 10-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 10"/></svg>
            </button>
            <button class="p-1.5 hover:bg-notion-hover dark:hover:bg-notion-hover-dark rounded-md text-notion-text-muted transition-colors" title="Archive">
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5" rx="1"/><line x1="10" y1="12" x2="14" y2="12"/></svg>
            </button>
            <button class="p-1.5 hover:bg-notion-hover dark:hover:bg-notion-hover-dark rounded-md text-notion-text-muted hover:text-red-600 transition-colors" title="Delete">
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
            </button>
        </div>
    </div>

    <!-- Thread Detail Body -->
    <div class="flex-1 overflow-y-auto p-8 space-y-6">
        <div class="space-y-4">
            <h2 class="text-xl font-bold text-gray-900 dark:text-white">{email.subject || "(no subject)"}</h2>
            <div class="flex items-center justify-between border-b border-gray-100 dark:border-gray-800 pb-4">
                <div class="flex items-center space-x-3">
                    <div class="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 font-semibold flex items-center justify-center text-sm">
                        {getSenderName(email).substring(0, 2)}
                    </div>
                    <div>
                        <div class="font-semibold text-sm text-gray-900 dark:text-gray-100">{getSenderName(email)}</div>
                        <div class="text-xs text-notion-text-muted">{getSenderEmail(email)}</div>
                    </div>
                </div>
                <span class="text-xs text-notion-text-muted">{new Date(email.date).toLocaleString()}</span>
            </div>
            <div class="pt-2 text-sm leading-relaxed text-gray-800 dark:text-gray-200 whitespace-pre-line">
                {email.body || ""}
            </div>
        </div>
    </div>

    <!-- Quick Reply Box -->
    <div class="p-4 border-t border-notion-border dark:border-notion-border-dark bg-gray-50/50 dark:bg-[#151515]">
        <div class="border border-notion-border dark:border-notion-border-dark rounded-lg bg-white dark:bg-[#202020] p-3 shadow-2xs">
            <textarea bind:value={replyText} placeholder="Write a reply..." class="w-full bg-transparent text-sm resize-none focus:outline-none text-gray-800 dark:text-gray-200 h-16"></textarea>
            <div class="flex items-center justify-between pt-2 border-t border-gray-100 dark:border-gray-800">
                <div class="flex items-center space-x-1">
                    <button class="p-1 text-gray-400 hover:text-gray-600 rounded">
                        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                    </button>
                </div>
                <button
                    class="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs font-medium transition-colors flex items-center space-x-1 disabled:opacity-50"
                    on:click={sendReply}
                    disabled={!replyText.trim()}
                >
                    <span>Send</span>
                    <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                </button>
            </div>
        </div>
    </div>
</div>
