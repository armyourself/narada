<script lang="ts" module>
    let isDraftChangedAfterLastSave = false;

    export function triggerDraftChange() {
        isDraftChangedAfterLastSave = true;
    }
</script>

<script lang="ts">
    import { SharedStore } from "$lib/stores/shared.svelte";
    import { local } from "$lib/locales";
    import { isStandardFolder } from "$lib/utils";
    import {
        AUTOSAVE_DRAFT_INTERVAL_MS,
        DEFAULT_LANGUAGE,
        SEND_RECALL_DELAY_MS,
    } from "$lib/constants";
    import {
        Folder,
        type Account,
        type OriginalMessageContext,
    } from "$lib/types";
    import { MailboxController } from "$lib/mailbox";
    import { onMount } from "svelte";
    import { WYSIWYGEditor } from "@bberkay/wysiwygeditor";
    import Form from "$lib/ui/Components/Form";
    import Mailbox, { getCurrentMailbox } from "$lib/ui/Layout/Main/Content/Mailbox.svelte";
    import { showThis as showContent } from "$lib/ui/Layout/Main/Content.svelte";
    import { show as showMessage } from "$lib/ui/Components/Message";
    import { show as showConfirm } from "$lib/ui/Components/Confirm";
    import { show as showToast } from "$lib/ui/Components/Toast";
    import Sender from "./Compose/Sender.svelte";
    import Receivers from "./Compose/Receivers.svelte";
    import Cc from "./Compose/Cc.svelte";
    import Bcc from "./Compose/Bcc.svelte";
    import Subject from "./Compose/Subject.svelte";
    import Body from "./Compose/Body.svelte";
    import Attachments from "./Compose/Attachments.svelte";
    import Action from "./Compose/Action.svelte";
    import Icon from "$lib/ui/Components/Icon";
    import { backToDefault } from "$lib/ui/Layout/Main/Content.svelte";
    import * as Button from "$lib/ui/Components/Button";
    import { nostrIdentity } from "$lib/nostr/identity.svelte";

    interface Props {
        originalMessageContext?: OriginalMessageContext;
        initialReceiver?: string;
    }

    let { originalMessageContext, initialReceiver }: Props = $props();

    let composeForm: HTMLFormElement | undefined = $state();
    let senderAccount: Account = $state(
        SharedStore.currentAccount !== "home"
            ? SharedStore.currentAccount
            : SharedStore.accounts[0],
    );
    let receiverList: string[] = $state(initialReceiver ? [initialReceiver] : []);
    let ccList: string[] = $state([]);
    let bccList: string[] = $state([]);
    let subject = $state("");
    let body: WYSIWYGEditor | undefined = $state();

    let isSendingEmail: boolean = $state(false);
    let isSavingDraft: boolean = $state(false);
    let draftAppenduid: string = "";
    let lastDraftSavedTime: string = $state("");

    onMount(() => {
        // TODO: Open this later...
        //startAutosaveDraftLoop();
    });

    function startAutosaveDraftLoop() {
        const loop = async () => {
            await saveDraft();
            setTimeout(loop, AUTOSAVE_DRAFT_INTERVAL_MS);
        };
        loop();
    }

    function createDraft(): FormData {
        const formData = new FormData(composeForm);
        formData.set("sender", senderAccount.email_address);
        formData.set("receivers", receiverList.join(","));
        formData.set("cc", ccList.join(","));
        formData.set("bcc", bccList.join(","));
        formData.set("body", body!.getHTMLContent());
        return formData;
    }

    async function deleteDraft() {
        await MailboxController.deleteDraft(senderAccount, draftAppenduid);
    }

    async function showSentMailbox() {
        if (senderAccount !== SharedStore.currentAccount) {
            SharedStore.currentAccount = senderAccount;
        }

        // Show sent folder of sender which must be the currentAccount
        // at this point.
        if (
            !isStandardFolder(
                getCurrentMailbox().folder,
                Folder.Sent,
            )
        ) {
            const response = await MailboxController.getMailbox(
                SharedStore.currentAccount,
                Folder.Sent,
            );

            if (!response.success) {
                showMessage({
                    title: local.error_sent_mailbox_after_sending_emails[
                        DEFAULT_LANGUAGE
                    ],
                });
                console.error(response.message);
                return;
            }
        }

        showContent(Mailbox);
    }

    async function sendEmail() {
        if (isSendingEmail || isSavingDraft) return;

        const sendTimeout = setTimeout(async () => {
            isSendingEmail = true;

            await deleteDraft();
            const draft = createDraft();

            // Check if all recipients are Nostr pubkeys
            const allRecipients = [
                ...receiverList,
                ...ccList,
            ];
            const isNostrSend = allRecipients.length > 0 && allRecipients.every(
                (r) => isNostrPubkey(r.trim())
            );

            let response;
            if (isNostrSend) {
                // Send via Nostr relays
                response = await sendNostrEmail(draft);
            } else if (originalMessageContext?.composeType === "reply") {
                response = await MailboxController.replyEmail(
                    originalMessageContext.messageId,
                    draft,
                );
            } else if (originalMessageContext?.composeType === "forward") {
                response = await MailboxController.forwardEmail(
                    originalMessageContext.messageId,
                    draft,
                );
            } else {
                response = await MailboxController.sendEmail(draft);
            }

            isSendingEmail = false;
            if (!response.success) {
                showMessage({
                    title: local.error_send_email_s[DEFAULT_LANGUAGE],
                });
                console.error(response.message);
                return;
            }

            showSentMailbox();
            showToast({ content: isNostrSend ? "Message sent via Nostr" : "Email sent" });
        }, SEND_RECALL_DELAY_MS);

        showToast({
            content: "Sending...",
            autoCloseDelay: SEND_RECALL_DELAY_MS,
            onUndo: () => {
                clearTimeout(sendTimeout);
            },
        });
    }

    function isNostrPubkey(value: string): boolean {
        const v = value.trim();
        if (v.startsWith("npub1")) return true;
        if (/^[0-9a-fA-F]{64}$/.test(v)) return true;
        return false;
    }

    async function sendNostrEmail(draft: FormData): Promise<{ success: boolean; message: string }> {
        try {
            const senderNpub = nostrIdentity.state.npub || "";
            const recipients = receiverList.map((r) => r.trim());
            const body = draft.get("body") as string || "";
            const subject = draft.get("subject") as string || "";

            const res = await fetch(`${SharedStore.server}/nostr/send-email`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    sender_npub: senderNpub,
                    recipient_npub: recipients[0],
                    subject,
                    body,
                    cc: ccList.map((c) => c.trim()),
                }),
            });
            const json = await res.json();
            return { success: json.success, message: json.message };
        } catch (err) {
            return { success: false, message: String(err) };
        }
    }

    const saveDraft = async () => {
        if (isSendingEmail || isSavingDraft || !isDraftChangedAfterLastSave)
            return;

        isSavingDraft = true;

        const draft = createDraft();
        const response = await MailboxController.saveDraft(
            draft,
            draftAppenduid,
        );

        if (response.success && response.data) {
            draftAppenduid = response.data;
        } else {
            showMessage({
                title: local.error_save_email_s_as_draft[DEFAULT_LANGUAGE],
            });
            console.error(response.message);
        }

        isSavingDraft = false;
        isDraftChangedAfterLastSave = false;
        lastDraftSavedTime = new Date(Date.now()).toLocaleString();
    };

    const handleSendEmailForm = async () => {
        if (!senderAccount || receiverList.length === 0) {
            showMessage({
                title: "Provide at least one sender and one receiver.",
            });
            console.error("Provide at least one sender and one receiver.");
            return;
        }

        if (!subject) {
            showConfirm({
                title: local.are_you_certain_subject_is_empty[DEFAULT_LANGUAGE],
                onConfirmText: local.yes_send[DEFAULT_LANGUAGE],
                onConfirm: sendEmail,
            });
            return;
        }

        if (!body!.getHTMLContent()) {
            showConfirm({
                title: local.are_you_certain_body_is_empty[DEFAULT_LANGUAGE],
                onConfirmText: local.yes_send[DEFAULT_LANGUAGE],
                onConfirm: sendEmail,
            });
            return;
        }

        await sendEmail();
    };
</script>

<div class="compose">
    <Button.Basic type="button" class="btn-inline" onclick={backToDefault}>
        <Icon name="back" />
    </Button.Basic>

    <h2 class="compose-title">Compose</h2>
    <Form
        class="compose-form"
        bind:element={composeForm}
        onsubmit={handleSendEmailForm}
    >
        <Sender bind:senderAccount />
        <Receivers bind:receiverList {originalMessageContext} />
        <Cc bind:ccList />
        <Bcc bind:bccList />
        <Subject bind:value={subject} {originalMessageContext} />
        <Body bind:editor={body} {originalMessageContext} />
        <Attachments />
        <Action
            bind:isSendingEmail
            bind:isSavingDraft
            {saveDraft}
            {deleteDraft}
        />
    </Form>
    {#if lastDraftSavedTime}
        <span class="draft-saved-feedback">
            Draft saved at {lastDraftSavedTime}
        </span>
    {/if}
</div>

<style>
    :global {
        .compose {
            position: absolute;
            bottom: 22px;
            right: 22px;
            width: 420px;
            max-width: calc(100vw - 44px);
            background: var(--glass-strong);
            backdrop-filter: blur(22px) saturate(1.5);
            -webkit-backdrop-filter: blur(22px) saturate(1.5);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius);
            box-shadow: 0 20px 50px rgba(160, 90, 50, 0.22);
            z-index: 200;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .compose .compose-form {
            overflow-x: hidden;
            overflow-y: auto;
            flex: 1;
        }

        .compose .compose-title {
            font-family: var(--ui);
            font-size: 0.82rem;
            font-weight: 600;
            padding: 12px 16px;
            border-bottom: 1px solid var(--glass-border);
        }
    }
</style>
