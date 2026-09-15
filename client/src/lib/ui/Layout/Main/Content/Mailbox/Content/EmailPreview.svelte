<script lang="ts" module>
    import { SharedStore } from "$lib/stores/shared.svelte";
    import { compactEmailDate, createDomElement } from "$lib/utils";
    import type { Account, Email as TEmail } from "$lib/types";

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
    import { onMount } from "svelte";
    import { MailboxController } from "$lib/mailbox";
    import { Mark } from "$lib/types";
    import { extractEmailAddress, extractFullname, truncate } from "$lib/utils";
    import { getMailboxContext } from "$lib/ui/Layout/Main/Content/Mailbox";
    import * as Input from "$lib/ui/Components/Input";
    import Email from "$lib/ui/Layout/Main/Content/Email.svelte";
    import { showThis as showContent } from "$lib/ui/Layout/Main/Content.svelte";
    import { show as showMessage } from "$lib/ui/Components/Message";
    import { show as showToast } from "$lib/ui/Components/Toast";
    import { local } from "$lib/locales";
    import { DEFAULT_LANGUAGE } from "$lib/constants";
    import { getCurrentMailbox } from "$lib/ui/Layout/Main/Content/Mailbox.svelte";
    import { GravatarService } from "$lib/services/GravatarService";
    import { Spinner } from "$lib/ui/Components/Loader";
    import RouteBadge, { emailRoute } from "$lib/ui/Components/RouteBadge.svelte";
    import {
        markEmails,
        unmarkEmails,
    } from "$lib/ui/Layout/Main/Content/Mailbox/Toolbox/Operations/MarkAs.svelte";
    import type { GroupedUidSelection } from "$lib/ui/Layout/Main/Content/Mailbox.svelte";

    const AVATAR_COLORS = ["#C99B76", "#A97635", "#4C7A61", "#8FA9C4", "#B98CA0", "#7C6A5E"];

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
    let isStarred = $derived(!!email.flags?.includes(Mark.Flagged));

    let initial = $derived((senderName[0] ?? "?").toUpperCase());
    let avatarColor = $derived.by(() => {
        // Deterministic color per sender address so a contact's avatar
        // stays stable across renders and mailboxes.
        const addr = extractEmailAddress(email.sender) || email.sender;
        let hash = 0;
        for (let i = 0; i < addr.length; i++) {
            hash = (hash * 31 + addr.charCodeAt(i)) >>> 0;
        }
        return AVATAR_COLORS[hash % AVATAR_COLORS.length];
    });

    async function toggleStar(e: Event) {
        e.stopPropagation();
        const groupedSelection: GroupedUidSelection = [
            [account.email_address, email.uid],
        ];
        if (isStarred) {
            await unmarkEmails(groupedSelection, Mark.Flagged, folder, false);
        } else {
            await markEmails(groupedSelection, Mark.Flagged, folder, false);
        }
    }
</script>

<div
    class="email-item"
    class:unread={isUnread}
    class:active={isSelected}
    onclick={showEmailContent}
    onkeydown={showEmailContent}
    tabindex="0"
    role="button"
>
    <div class="avatar" style="background:{avatarColor};">{initial}</div>
    <div class="email-content">
        <div class="email-top">
            <span class="email-name">{senderName}</span>
            <span class="email-time">{compactEmailDate(email.date)}</span>
        </div>
        <div class="email-preview">{truncate(email.body, MAX_BODY_LENGTH)}</div>
        <div class="email-meta-row">
            <RouteBadge route={emailRoute(email)} />
            {#if hasAttachments}
                <span class="attach-note">
                    <svg viewBox="0 0 24 24"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                </span>
            {/if}
        </div>
    </div>
    <div class="email-right">
        <button
            class="star-icon"
            class:active={isStarred}
            onclick={toggleStar}
            title={isStarred ? "Unstar" : "Star"}
            aria-label={isStarred ? "Unstar" : "Star"}
        >
            <svg viewBox="0 0 24 24"><path d="M12 3l2.6 5.9 6.4.6-4.8 4.3 1.4 6.3L12 17l-5.6 3.1 1.4-6.3-4.8-4.3 6.4-.6L12 3Z"/></svg>
        </button>
        {#if isUnread}
            <span class="unread-dot"></span>
        {/if}
    </div>
</div>
<style>
    :global {
        .email-item {
            padding: 13px 12px;
            display: flex;
            gap: 12px;
            border-radius: var(--radius-sm);
            cursor: pointer;
            transition: background 0.15s ease;
            position: relative;
        }

        .email-item:hover {
            background: var(--glass-strong);
        }

        .email-item.active {
            background: var(--glass-strong);
            box-shadow: inset 2px 0 0 var(--accent);
        }

        .email-item .avatar {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            font-size: 0.72rem;
            font-family: var(--ui);
            font-weight: 600;
            flex-shrink: 0;
        }

        .email-item .email-content {
            flex-grow: 1;
            min-width: 0;
        }

        .email-item .email-top {
            display: flex;
            justify-content: space-between;
            margin-bottom: 3px;
            gap: 6px;
        }

        .email-item .email-name {
            font-weight: 500;
            font-size: 0.85rem;
            color: var(--ink-dim);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .email-item.unread .email-name {
            font-weight: 600;
            color: var(--ink);
        }

        .email-item .email-time {
            font-size: 0.66rem;
            color: var(--ink-faint);
            font-family: var(--ui);
            flex-shrink: 0;
        }

        .email-item .email-preview {
            font-size: 0.78rem;
            color: var(--ink-faint);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            margin-bottom: 5px;
        }

        .email-item .email-meta-row {
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .email-item .email-right {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            justify-content: space-between;
            flex-shrink: 0;
        }

        .email-item .star-icon {
            color: var(--ink-faint);
            display: flex;
            padding: 2px;
        }

        .email-item .star-icon:hover {
            color: var(--ink);
        }

        .email-item .star-icon.active {
            color: var(--accent);
        }

        .email-item .star-icon svg {
            width: 13px;
            height: 13px;
            stroke: currentColor;
            fill: none;
            stroke-width: 2;
        }

        .email-item .star-icon.active svg {
            fill: currentColor;
        }

        .email-item .unread-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--accent);
        }

        .email-item .attach-note svg {
            width: 12px;
            height: 12px;
            stroke: var(--ink-faint);
            fill: none;
            stroke-width: 2;
        }
    }
</style>
