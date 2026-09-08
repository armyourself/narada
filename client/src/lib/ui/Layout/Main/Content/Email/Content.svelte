<script lang="ts">
    import { type Account, type Email } from "$lib/types";
    import Body from "./Content/Body.svelte";
    import Attachments from "./Content/Attachments.svelte";
    import Subject from "./Content/Subject.svelte";
    import Flags from "./Content/Flags.svelte";
    import Sender from "./Content/Sender.svelte";
    import { getCurrentMailbox } from "$lib/ui/Layout/Main/Content/Mailbox.svelte";
    import { extractFullname, extractEmailAddress } from "$lib/utils";

    interface Props {
        account: Account;
        email: Email;
    }

    let { account, email }: Props = $props();

    let senderName = $derived(extractFullname(email.sender) || extractEmailAddress(email.sender));
    let senderEmail = $derived(extractEmailAddress(email.sender));
    let initial = $derived(senderName[0]?.toUpperCase() || "?");
</script>

<div class="reading-panel">
    <div class="reading-head">
        <div class="reading-subject">{email.subject}</div>
        <div class="reading-from">
            <div class="avatar">{initial}</div>
            <div class="reading-from-meta">
                <div class="name">{senderName}</div>
                <div class="addr">{senderEmail}</div>
            </div>
            <div class="reading-time">{new Date(email.date).toLocaleDateString()}</div>
        </div>
        <div class="route-strip">
            <span class="badge">
                <svg viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>
                Encrypted
            </span>
        </div>
    </div>
    <div class="reading-body">
        <Body {email} />
    </div>
    {#if email.attachments}
        <div class="reading-actions">
            <Attachments
                {account}
                {email}
                folder={getCurrentMailbox().folder}
            />
        </div>
    {/if}
</div>

<style>
    :global {
        .reading-panel {
            position: absolute;
            top: 88px;
            left: 662px;
            right: 22px;
            bottom: 22px;
            z-index: 2;
            background: var(--glass);
            backdrop-filter: blur(18px) saturate(1.4);
            -webkit-backdrop-filter: blur(18px) saturate(1.4);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius);
            box-shadow: var(--shadow);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .reading-head {
            padding: 16px 22px 14px;
            border-bottom: 1px solid var(--glass-border);
            flex-shrink: 0;
        }

        .reading-subject {
            font-family: var(--ui);
            font-size: 1.05rem;
            font-weight: 600;
            margin-bottom: 12px;
        }

        .reading-from {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .reading-from .avatar {
            width: 34px;
            height: 34px;
            border-radius: 50%;
            background: linear-gradient(145deg, var(--accent-soft), var(--accent));
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            font-family: var(--ui);
            font-weight: 600;
            font-size: 0.8rem;
            flex-shrink: 0;
        }

        .reading-from-meta {
            flex: 1;
            min-width: 0;
        }

        .reading-from-meta .name {
            font-size: 0.85rem;
            font-weight: 600;
        }

        .reading-from-meta .addr {
            font-size: 0.7rem;
            color: var(--ink-faint);
            font-family: var(--ui);
        }

        .reading-time {
            font-size: 0.7rem;
            color: var(--ink-faint);
            font-family: var(--ui);
            white-space: nowrap;
        }

        .route-strip {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-top: 12px;
            flex-wrap: wrap;
        }

        .route-strip .badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-family: var(--ui);
            font-size: 0.66rem;
            color: var(--ink-dim);
            background: var(--glass-strong);
            border: 1px solid var(--glass-border);
            padding: 4px 10px;
            border-radius: 100px;
        }

        .route-strip .badge svg {
            width: 10px;
            height: 10px;
            stroke: currentColor;
            fill: none;
            stroke-width: 2.2;
        }

        .reading-body {
            flex: 1;
            overflow-y: auto;
            padding: 18px 22px 24px;
            font-size: 0.9rem;
            line-height: 1.7;
            color: var(--ink);
        }

        .reading-body::-webkit-scrollbar { width: 6px; }
        .reading-body::-webkit-scrollbar-thumb { background: rgba(180, 140, 110, 0.25); border-radius: 10px; }

        .reading-body p + p { margin-top: 12px; }

        .reading-actions {
            display: flex;
            gap: 10px;
            padding: 14px 22px 18px;
            border-top: 1px solid var(--glass-border);
            flex-shrink: 0;
            flex-wrap: wrap;
        }

        .action-btn {
            display: flex;
            align-items: center;
            gap: 8px;
            background: var(--glass-strong);
            border: 1px solid var(--glass-border);
            padding: 8px 14px;
            border-radius: 100px;
            font-size: 0.78rem;
            color: var(--ink-dim);
            transition: background 0.15s ease, color 0.15s ease;
        }

        .action-btn:hover {
            background: #fff;
            color: var(--ink);
        }

        .action-btn svg {
            width: 14px;
            height: 14px;
            stroke: currentColor;
            fill: none;
            stroke-width: 2;
        }
    }
</style>
