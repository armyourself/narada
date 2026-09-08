<script lang="ts">
    import { onMount } from "svelte";
    import { close, type Props } from "./index";
    import * as Button from "$lib/ui/Components/Button";
    import { combine } from "$lib/utils";
    import { local } from "$lib/locales";
    import { DEFAULT_LANGUAGE } from "$lib/constants";

    let {
        title,
        onConfirmText,
        onConfirm,
        details,
        onCancelText,
        onCancel,
        ...attributes
    }: Props = $props();

    let {
	    class: additionalClass,
		...restAttributes
	} = $derived(attributes);

    onMount(() => {
        document.documentElement.scrollTop = 0;
        document.body.scrollTop = 0;
    });

    const onCancelWrapper = async (e: Event): Promise<void> => {
        if (onCancel) await onCancel(e);
        close();
    };

    const onConfirmWrapper = async (e: Event): Promise<void> => {
        await onConfirm(e);
        close();
    };
</script>

<div
    class={combine("modal confirm", additionalClass)}
    {...restAttributes}
>
    <div class="confirm-card">
        <h3>{title}</h3>
        {#if details}
            <p>{@html details}</p>
        {/if}
        <div class="confirm-actions">
            <Button.Action
                type="button"
                class="btn-outline"
                onclick={onCancelWrapper}
            >
                {onCancelText || local.cancel[DEFAULT_LANGUAGE]}
            </Button.Action>
            <Button.Action
                type="button"
                class="btn-cta"
                onclick={onConfirmWrapper}
            >
                {onConfirmText}
            </Button.Action>
        </div>
    </div>
</div>

<style>
    :global {
        .modal.confirm {
            opacity: 1;
        }

        .confirm-card {
            background: var(--glass-strong);
            backdrop-filter: blur(22px) saturate(1.5);
            -webkit-backdrop-filter: blur(22px) saturate(1.5);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius);
            box-shadow: var(--shadow-lg);
            padding: var(--spacing-lg);
            max-width: 420px;
            width: 100%;

            & h3 {
                font-family: var(--ui);
                font-size: 1rem;
                font-weight: 600;
                margin-bottom: var(--spacing-sm);
            }

            & p {
                font-size: var(--font-size-sm);
                color: var(--ink-dim);
                margin-bottom: var(--spacing-lg);
            }
        }

        .confirm-actions {
            display: flex;
            gap: var(--spacing-sm);
            justify-content: flex-end;
        }
    }
</style>
