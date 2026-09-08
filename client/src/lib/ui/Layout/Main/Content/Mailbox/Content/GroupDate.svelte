<script lang="ts">
    interface Props {
        groupDate: string;
    }

    let { groupDate }: Props = $props();
</script>

<div class="email-preview-group-separator">
    <div class="timeline-label">
        <span>{groupDate}</span>
    </div>
</div>

<style>
    :global {
        .mailbox .email-preview-group-separator {
            width: 100%;
            color: var(--ink-faint);
            font-size: 0.68rem;
            font-family: var(--ui);
            padding: 10px 12px 6px;
            text-align: left;
            font-weight: 600;
            letter-spacing: 0.02em;
        }
    }
</style>
