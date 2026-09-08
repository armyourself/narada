<script lang="ts" module>
    import { SharedStore } from "$lib/stores/shared.svelte";
    import { compactEmailDate, createDomElement } from "$lib/utils";

    export function findAccountByEmail(email: TEmail): Account | undefined {
        if (SharedStore.currentAccount !== "home") {
            return SharedStore.currentAccount;
        }

        return SharedStore.accounts.find((acc) =>
            SharedStore.mailboxes[acc.email_address].emails.current.find(
                (em) => em.uid === email.uid,
            ),
        );
    }

    export function isRecentEmail(account: Account, email: TEmail): boolean {
        return (
            Object.hasOwn(
                SharedStore.recentEmailsChannel,
                account.email_address,
            ) &&
            SharedStore.recentEmailsChannel[account.email_address].findIndex(
                (em) => em.uid === email.uid,
            ) !== -1
        );
    }
</script>

<script lang="ts">
    import { mount, onMount, unmount } from "svelte";
    import { MailboxController } from "$lib/mailbox";
    import { type Email as TEmail, type Account } from "$lib/types";
    import { extractEmailAddress, extractFullname, truncate } from "$lib/utils";
    import { getMailboxContext } from "$lib/ui/Layout/Main/Content/Mailbox";
    import * as Input from "$lib/ui/Components/Input";
    import Icon from "$lib/ui/Components/Icon";
    import Badge from "$lib/ui/Components/Badge/Badge.svelte";
    import Email from "$lib/ui/Layout/Main/Content/Email.svelte";
    import { showThis as showContent } from "$lib/ui/Layout/Main/Content.svelte";
    import { show as showMessage } from "$lib/ui/Components/Message";
    import { local } from "$lib/locales";
    import { DEFAULT_LANGUAGE } from "$lib/constants";
    import { getCurrentMailbox } from "$lib/ui/Layout/Main/Content/Mailbox.svelte";
    import { GravatarService } from "$lib/services/GravatarService";
    import { Spinner } from "$lib/ui/Components/Loader";

    const MAX_BODY_LENGTH = 150;

    interface Props {
        email: TEmail;
    }

    let { email }: Props = $props();

    const mailboxContext = getMailboxContext();
    const account = findAccountByEmail(email)!;
    const folder = getCurrentMailbox().folder;

    let isSelected = $state(false);
    let isHovered = $state(false);

    const showEmailContent = async (e: Event): Promise<void> => {
        const response = await MailboxController.getEmailContent(
            account,
            getCurrentMailbox().folder,
            email.uid,
        );

        mailboxContext.emailSelection.value = [];

        if (!response.success || !response.data) {
            showMessage({
                title: local.error_get_email_content[DEFAULT_LANGUAGE],
            });
            console.error(response.message);
            return;
        }

        showContent(Email, {
            account: account,
            email: response.data,
        });
    };

    function isEmailChecked() {
        return mailboxContext.emailSelection.value === "1:*" || mailboxContext.emailSelection.value.length > 0;
    }

    $effect(() => {
        isSelected = isEmailChecked();
    });

    let senderName = $derived(extractFullname(email.sender) || extractEmailAddress(email.sender));
    let hasAttachments = $derived(Object.hasOwn(email, "attachments") && email.attachments!.length > 0);
    let isUnread = $derived(!email.flags?.includes("\\Seen"));
</script>

<div
    class="mail-row"
    class:unread={isUnread}
    class:read={!isUnread}
    class:selected={isSelected}
    onclick={showEmailContent}
    onkeydown={showEmailContent}
    tabindex="0"
    role="button"
>
    <span class="unread-dot"></span>
    <div class="mail-body">
        <div class="mail-top">
            <span class="sender">{senderName}</span>
            <span class="time">{compactEmailDate(email.date)}</span>
        </div>
        <div class="subject">{email.subject}</div>
        <div class="snippet">{truncate(email.body, MAX_BODY_LENGTH)}</div>
        <div class="mail-meta">
            {#if hasAttachments}
                <span class="badge">
                    <svg viewBox="0 0 24 24"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                    Files
                </span>
            {/if}
            {#if email.flags?.includes("\\Flagged")}
                <span class="badge relay">
                    <svg viewBox="0 0 24 24"><path d="M12 3l2.6 5.9 6.4.6-4.8 4.3 1.4 6.3L12 17l-5.6 3.1 1.4-6.3-4.8-4.3 6.4-.6L12 3Z"/></svg>
                    Flagged
                </span>
            {/if}
        </div>
    </div>
</div>

<style>
    :global {
        .mail-row {
            display: flex;
            align-items: flex-start;
            gap: 11px;
            padding: 12px 12px;
            border-radius: var(--radius-sm);
            cursor: pointer;
            transition: background 0.15s ease;
            position: relative;
        }

        .mail-row:hover {
            background: var(--glass-strong);
        }

        .mail-row.selected {
            background: var(--glass-strong);
            box-shadow: inset 0 0 0 1px var(--glass-border);
        }

        .mail-row.unread .sender,
        .mail-row.unread .subject {
            font-weight: 600;
            color: var(--ink);
        }

        .mail-row .unread-dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: var(--accent);
            margin-top: 6px;
            flex-shrink: 0;
        }

        .mail-row.read .unread-dot {
            background: transparent;
        }

        .mail-body {
            flex: 1;
            min-width: 0;
        }

        .mail-top {
            display: flex;
            justify-content: space-between;
            gap: 8px;
        }

        .sender {
            font-size: 0.85rem;
            color: var(--ink-dim);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .time {
            font-size: 0.68rem;
            color: var(--ink-faint);
            flex-shrink: 0;
            font-family: var(--ui);
        }

        .subject {
            font-size: 0.83rem;
            color: var(--ink-dim);
            margin-top: 2px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .snippet {
            font-size: 0.78rem;
            color: var(--ink-faint);
            margin-top: 2px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .mail-meta {
            display: flex;
            align-items: center;
            gap: 6px;
            margin-top: 6px;
            flex-wrap: wrap;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-family: var(--ui);
            font-size: 0.62rem;
            color: var(--ink-dim);
            background: var(--glass-strong);
            border: 1px solid var(--glass-border);
            padding: 2px 8px;
            border-radius: 100px;
        }

        .badge svg {
            width: 10px;
            height: 10px;
            stroke: currentColor;
            fill: none;
            stroke-width: 2.2;
        }

        .badge.relay {
            color: #A97635;
            border-style: dashed;
            border-color: rgba(169, 118, 53, 0.45);
            background: rgba(169, 118, 53, 0.09);
        }
    }
</style>
