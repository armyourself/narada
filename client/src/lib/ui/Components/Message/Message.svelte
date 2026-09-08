<script lang="ts">
    import { onMount } from "svelte";
    import { close, type Props } from "./index";
    import { combine } from "$lib/utils";
    import * as Button from "$lib/ui/Components/Button";
    import { local } from "$lib/locales";
    import { DEFAULT_LANGUAGE } from "$lib/constants";

    let {
        title,
        details,
        onCloseText,
        onClose,
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

    const onCloseWrapper = async (e: Event) => {
        if (onClose) await onClose(e);
        close();
    };
</script>

<div
    class={combine("modal message", additionalClass)}
    {...restAttributes}
>
    <div class="message-card">
        <h3>{title}</h3>
        {#if details}
            <p>{@html details}</p>
        {/if}
        <Button.Action
            type="button"
            class="btn-outline"
            onclick={onCloseWrapper}
        >
            {onCloseText || local.close[DEFAULT_LANGUAGE]}
        </Button.Action>
    </div>
</div>

<style>
    :global {
        .modal.message {
            opacity: 1;
        }

        .message-card {
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
    }
</style>
