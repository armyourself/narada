<script lang="ts">
    import { SharedStore } from "$lib/stores/shared.svelte";
    import { show as showMessage } from "$lib/ui/Components/Message";
    import { show as showToast } from "$lib/ui/Components/Toast";
    import { nostrIdentity } from "$lib/nostr/identity.svelte";
    import type { Account } from "$lib/types";

    interface Props {
        onClose: () => void;
    }

    let { onClose }: Props = $props();

    let to = $state("");
    let subject = $state("");
    let body = $state("");
    let isSending = $state(false);

    let currentAccount = $derived(
        SharedStore.currentAccount !== "home"
            ? (SharedStore.currentAccount as Account)
            : SharedStore.accounts[0],
    );

    function isNostrPubkey(value: string): boolean {
        const v = value.trim();
        if (v.startsWith("npub1")) return true;
        if (/^[0-9a-fA-F]{64}$/.test(v)) return true;
        return false;
    }

    async function sendEmail() {
        if (!to.trim()) {
            showMessage({ title: "Please specify a recipient." });
            return;
        }
        if (!subject.trim()) {
            showMessage({ title: "Please specify a subject." });
            return;
        }

        isSending = true;
        try {
            if (isNostrPubkey(to)) {
                const senderNpub = nostrIdentity.state.npub || "";
                const res = await fetch(`${SharedStore.server}/nostr/send-email`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        sender_npub: senderNpub,
                        recipient_npub: to.trim(),
                        subject: subject.trim(),
                        body: body.trim(),
                    }),
                });
                const json = await res.json();
                if (json.success) {
                    showToast({ content: "Message sent via Nostr" });
                    onClose();
                } else {
                    showMessage({ title: json.message || "Failed to send" });
                }
            } else {
                const formData = new FormData();
                formData.set("sender", currentAccount?.email_address || "");
                formData.set("receivers", to.trim());
                formData.set("subject", subject.trim());
                formData.set("body", body.trim());
                const { MailboxController } = await import("$lib/mailbox");
                const response = await MailboxController.sendEmail(formData);
                if (response.success) {
                    showToast({ content: "Email sent" });
                    onClose();
                } else {
                    showMessage({ title: response.message || "Failed to send" });
                }
            }
        } catch (err) {
            showMessage({ title: String(err) });
        } finally {
            isSending = false;
        }
    }

    function handleKeydown(e: KeyboardEvent) {
        if (e.key === "Escape") onClose();
    }
</script>

<svelte:window on:keydown={handleKeydown} />

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="fixed inset-0 bg-black/40 backdrop-blur-xs z-50 flex items-center justify-center p-4" onclick={onClose}>
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="bg-white dark:bg-[#1e1e1e] w-full max-w-2xl rounded-xl shadow-2xl border border-notion-border dark:border-notion-border-dark overflow-hidden flex flex-col" onclick={(e) => e.stopPropagation()}>
        <!-- Header -->
        <div class="px-4 py-3 border-b border-notion-border dark:border-notion-border-dark flex items-center justify-between bg-gray-50/50 dark:bg-[#181818]">
            <span class="text-sm font-semibold text-gray-800 dark:text-gray-200">New Message</span>
            <button class="text-notion-text-muted hover:text-gray-800 dark:hover:text-gray-200" onclick={onClose}>
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
        </div>
        <!-- Form -->
        <div class="p-4 space-y-3">
            <div class="flex items-center border-b border-gray-100 dark:border-gray-800 pb-2">
                <span class="text-xs text-notion-text-muted w-16">To:</span>
                <input type="text" bind:value={to} placeholder="Recipient email or npub" class="w-full text-sm bg-transparent focus:outline-none text-gray-800 dark:text-gray-200" />
            </div>
            <div class="flex items-center border-b border-gray-100 dark:border-gray-800 pb-2">
                <span class="text-xs text-notion-text-muted w-16">Subject:</span>
                <input type="text" bind:value={subject} placeholder="Email subject" class="w-full text-sm bg-transparent focus:outline-none text-gray-800 dark:text-gray-200" />
            </div>
            <textarea bind:value={body} placeholder="Write your email here..." class="w-full h-48 bg-transparent text-sm focus:outline-none resize-none pt-2 text-gray-800 dark:text-gray-200"></textarea>
        </div>
        <!-- Footer -->
        <div class="px-4 py-3 border-t border-notion-border dark:border-notion-border-dark bg-gray-50/50 dark:bg-[#181818] flex items-center justify-between">
            <div></div>
            <div class="flex items-center space-x-2">
                <button class="px-3 py-1.5 text-xs text-gray-600 dark:text-gray-400 hover:bg-notion-hover dark:hover:bg-notion-hover-dark rounded transition-colors" onclick={onClose}>Discard</button>
                <button
                    class="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs font-medium transition-colors flex items-center space-x-1 disabled:opacity-50"
                    onclick={sendEmail}
                    disabled={isSending}
                >
                    <span>{isSending ? "Sending..." : "Send"}</span>
                    <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                </button>
            </div>
        </div>
    </div>
</div>
